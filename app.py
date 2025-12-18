import streamlit as st
import pandas as pd
import sqlite3
import requests
import datetime
import io
import plotly.express as px

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="SMART FINANCE PRO 2026", layout="wide")

DB_NAME = "finanzas_2026.db"

# --- FUNCIONES DE FORMATEO (ESTILO ARGENTINA) ---
def formato_ar(valor):
    """Formato: $ 1.250.300,50"""
    if valor is None or pd.isna(valor): return "$ 0,00"
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"

def procesar_monto(texto):
    if not texto: return 0.0
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError: return 0.0

# --- BASE DE DATOS Y RECUPERACIÓN ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, mes TEXT, 
                  tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT,
                  forma_pago TEXT, fecha_pago TEXT)''')
    
    # Motor de rescate automático
    c.execute("SELECT COUNT(*) FROM movimientos")
    if c.fetchone()[0] == 0:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mov%' AND name != 'movimientos'")
        viejas = [t[0] for t in c.fetchall()]
        for t in viejas:
            try:
                c.execute(f"INSERT INTO movimientos (mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) "
                          f"SELECT mes, tipo, grupo, tipo_gasto, IFNULL(cuota, '1/1'), monto, moneda, forma_pago, fecha_pago FROM {t}")
                conn.commit()
            except: continue

    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

# --- CONSTANTES Y API ---
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]
OPCIONES_TIPO = ["GANANCIA", "GASTO", "AHORRO"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

@st.cache_data(ttl=3600)
def get_dolar():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=5).json()
        compra = float(r['compra'])
        venta = float(r['venta'])
        promedio = (compra + venta) / 2
        # Formato de detalle con $ y puntuación AR
        det = f"(Compra: {formato_ar(compra)} | Venta: {formato_ar(venta)})"
        return promedio, det
    except: return 1490.0, "(API fuera de servicio)"

dolar_val, dolar_info = get_dolar()

# --- INTERFAZ ---
st.title("SMART FINANCE PRO 2026")
# Selector Global (Este manda sobre la carga y la vista)
mes_global = st.selectbox("📅 SELECCIONAR MES DE TRABAJO:", MESES)

# --- SIDEBAR: CARGAR MOVIMIENTO (SIN SELECTOR DE MES) ---
st.sidebar.header("📥 CARGAR MOVIMIENTO")
st.sidebar.info(f"Registrando en: **{mes_global}**")

conn = sqlite3.connect(DB_NAME)
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
conn.close()

with st.sidebar.form("form_carga", clear_on_submit=True):
    t_sel = st.selectbox("TIPO", OPCIONES_TIPO)
    g_sel = st.selectbox("GRUPO", grupos_db)
    concepto = st.text_input("CONCEPTO")
    cuota_in = st.text_input("CUOTA", value="1/1")
    m_input = st.text_input("MONTO (Ej: 852.300,50)", value="0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("FORMA DE PAGO", OPCIONES_PAGO)
    f_pago_date = st.date_input("FECHA DE PAGO", value=datetime.date(2026, 1, 1),
                                min_value=datetime.date(2026, 1, 1), max_value=datetime.date(2026, 12, 31))
    
    if st.form_submit_button("GRABAR"):
        if not grupos_db:
            st.error("Primero configurá los GRUPOS en la otra pestaña.")
        else:
            m_final = procesar_monto(m_input)
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (str(datetime.date.today()), mes_global, t_sel, g_sel, concepto, cuota_in, m_final, mon_sel, f_pago, str(f_pago_date)))
            conn.commit()
            conn.close()
            st.success(f"¡Grabado en {mes_global}!")
            st.rerun()

# --- DASHBOARD ---
tab_dash, tab_conf = st.tabs(["🚀 DASHBOARD ANALÍTICO", "🛠️ CONFIGURAR GRUPOS"])

with tab_dash:
    st.info(f"💵 DÓLAR BLUE PROMEDIO: **{formato_ar(dolar_val)}** {dolar_info}")
    
    conn = sqlite3.connect(DB_NAME)
    df_all = pd.read_sql("SELECT * FROM movimientos", conn)
    conn.close()
    
    if not df_all.empty:
        df_all['monto_ars'] = df_all.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        
        # Balance (Ahorro suma)
        balances = {}
        acumulado = 0.0
        for m in MESES:
            m_data = df_all[df_all['mes'] == m]
            bal_mes = m_data[m_data['tipo'] == "GANANCIA"]['monto_ars'].sum() - \
                      m_data[m_data['tipo'] == "GASTO"]['monto_ars'].sum() + \
                      m_data[m_data['tipo'] == "AHORRO"]['monto_ars'].sum()
            acumulado += bal_mes
            balances[m] = acumulado
        
        c1, c2, c3 = st.columns([2, 2, 1])
        c1.metric("SALDO PROYECTADO", formato_ar(balances[mes_global]))
        c2.metric("EN USD BLUE", f"US$ {formato_ar(balances[mes_global]/dolar_val).replace('$','')}")
        
        with c3:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_all.to_excel(writer, index=False)
            st.download_button("📥 EXCEL", buffer.getvalue(), f"Finanzas_2026.xlsx")

        st.divider()
        col_pie, col_bar = st.columns(2)
        df_mes = df_all[df_all['mes'] == mes_global].copy().reset_index(drop=True)

        with col_pie:
            st.subheader("Distribución de Gastos")
            gastos_mes = df_mes[df_mes['tipo'] == "GASTO"]
            if not gastos_mes.empty:
                fig_pie = px.pie(gastos_mes, values='monto_ars', names='grupo', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
            else: st.write("Sin gastos en este mes.")

        with col_bar:
            st.subheader("Ingresos vs Gastos")
            resumen = df_mes.groupby('tipo')['monto_ars'].sum().reset_index()
            fig_bar = px.bar(resumen, x='tipo', y='monto_ars', color='tipo',
                             color_discrete_map={"GANANCIA": "#28a745", "GASTO": "#dc3545", "AHORRO": "#007bff"})
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        st.subheader(f"DETALLE Y EDICIÓN - {mes_global.upper()}")
        busqueda = st.text_input("🔍 BUSCAR (CONCEPTO O GRUPO):", "").upper()
        
        if busqueda:
            df_mes = df_mes[df_mes['tipo_gasto'].str.upper().str.contains(busqueda, na=False) | 
                            df_mes['grupo'].str.upper().str.contains(busqueda, na=False)]
        
        # ORDEN DE COLUMNAS Y ETIQUETAS EN MAYÚSCULAS
        col_view = ["id", "grupo", "tipo_gasto", "cuota", "tipo", "moneda", "forma_pago", "fecha_pago", "monto_ars"]
        
        edited_df = st.data_editor(
            df_mes[col_view],
            hide_index=True,
            num_rows="dynamic",
            use_container_width=True,
            height=450,
            column_config={
                "id": None,
                "grupo": st.column_config.SelectboxColumn("GRUPO", options=grupos_db, required=True),
                "tipo_gasto": "CONCEPTO",
                "cuota": "CUOTA",
                "tipo": st.column_config.SelectboxColumn("TIPO", options=OPCIONES_TIPO, required=True),
                "moneda": st.column_config.SelectboxColumn("MONEDA", options=["ARS", "USD"], required=True),
                "forma_pago": st.column_config.SelectboxColumn("FORMA DE PAGO", options=OPCIONES_PAGO, required=True),
                "fecha_pago": "FECHA DE PAGO",
                "monto_ars": st.column_config.NumberColumn("MONTO ARS", format="$ %.2f")
            }
        )

        if st.button("💾 GUARDAR CAMBIOS"):
            conn = sqlite3.connect(DB_NAME)
            ids_visibles = df_mes['id'].dropna().tolist()
            if ids_visibles:
                conn.execute(f"DELETE FROM movimientos WHERE id IN ({','.join(['?']*len(ids_visibles))})", ids_visibles)
            df_to_save = edited_df.drop(columns=['monto_ars'])
            df_to_save['mes'] = mes_global
            df_to_save.to_sql("movimientos", conn, if_exists="append", index=False)
            conn.commit()
            conn.close()
            st.success("¡Datos guardados!")
            st.rerun()
    else:
        st.warning("SIN DATOS CARGADOS.")

with tab_conf:
    st.subheader("ADMINISTRAR GRUPOS")
    c_a, c_b = st.columns(2)
    with c_a:
        ng = st.text_input("NUEVO GRUPO").upper()
        if st.button("AÑADIR"):
            if ng:
                conn = sqlite3.connect(DB_NAME)
                conn.execute("INSERT OR IGNORE INTO grupos VALUES (?)", (ng,))
                conn.commit()
                conn.close()
                st.rerun()
    with c_b:
        conn = sqlite3.connect(DB_NAME)
        lista_g = pd.read_sql("SELECT nombre FROM grupos", conn)['nombre'].tolist()
        conn.close()
        if lista_g:
            g_del = st.selectbox("ELIMINAR GRUPO", lista_g)
            if st.button("BORRAR"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM grupos WHERE nombre = ?", (g_del,))
                conn.commit()
                conn.close()
                st.rerun()