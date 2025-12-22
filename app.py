import streamlit as st
import pandas as pd
import sqlite3
import requests
import datetime
import plotly.express as px
import hashlib

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SMART FINANCE PRO 2026", layout="wide")
DB_NAME = "finanzas_2026.db"

# --- FUNCIONES DE SEGURIDAD ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return resulting_hash
    return False

# --- FUNCIONES DE FORMATO ---
def formato_moneda_visual(valor, moneda):
    if valor is None or pd.isna(valor): return ""
    try:
        num = float(valor)
        s = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        prefijo = "US$ " if moneda == "USD" else "$ "
        return f"{prefijo}{s}"
    except: return str(valor)

def procesar_monto_input(texto):
    if not texto: return 0.0
    try:
        if isinstance(texto, (int, float)): return float(texto)
        t = str(texto).strip().replace("$", "").replace("US", "").replace(" ", "")
        return float(t.replace(".", "").replace(",", "."))
    except: return 0.0

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabla Movimientos
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, mes TEXT, 
                  tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT,
                  forma_pago TEXT, fecha_pago TEXT)''')
    
    # Tabla Grupos
    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    
    # Tabla Usuarios (NUEVA)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')

    # Datos Semilla Grupos
    c.execute("SELECT count(*) FROM grupos")
    if c.fetchone()[0] == 0:
        grupos_base = [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",)]
        c.executemany("INSERT OR IGNORE INTO grupos VALUES (?)", grupos_base)
        
    # Datos Semilla Usuario Admin (admin / admin123)
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        # La contraseña es "admin123" hasheada
        pwd_hash = make_hashes("admin123")
        c.execute("INSERT INTO users (username, password) VALUES (?,?)", ("admin", pwd_hash))

    conn.commit()
    conn.close()

init_db()

# --- CONSTANTES ---
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]

@st.cache_data(ttl=3600)
def get_dolar():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=5).json()
        info = f"(Compra:{int(r['compra'])} | Venta: ${int(r['venta'])})"
        return (float(r['compra']) + float(r['venta'])) / 2, info
    except: return 1480.0, "(Compra:1470 | Venta: $1490)"

# --- GESTIÓN DE SESIÓN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

# ==========================================
# SISTEMA DE LOGIN
# ==========================================
def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 SMART FINANCE ACCESS</h1>", unsafe_allow_html=True)
    st.write("")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit = st.form_submit_button("Ingresar", use_container_width=True)
            
            if submit:
                hashed_pswd = make_hashes(password)
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed_pswd))
                data = c.fetchall()
                conn.close()
                
                if data:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.success("Acceso concedido")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

# SI NO ESTÁ LOGUEADO -> MOSTRAR LOGIN Y DETENER
if not st.session_state['logged_in']:
    login_page()
    st.stop()  # Detiene la ejecución aquí para que no cargue el resto

# ==========================================
# APLICACIÓN PRINCIPAL (SOLO SI LOGUEADO)
# ==========================================

# Sidebar: Logout y Datos
with st.sidebar:
    st.write(f"👤 Usuario: **{st.session_state['username']}**")
    if st.button("Cerrar Sesión"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.divider()

dolar_val, dolar_info = get_dolar()

# --- CABECERA ---
st.title("SMART FINANCE PRO 2026")
mes_global = st.selectbox("📅 MES DE TRABAJO:", MESES)

# --- CARGA DE DATOS ---
conn = sqlite3.connect(DB_NAME)
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
df_all = pd.read_sql("SELECT * FROM movimientos", conn)
conn.close()

# --- SIDEBAR: ALTA NUEVA ---
st.sidebar.header("📥 CARGAR NUEVO")
with st.sidebar.form("form_carga", clear_on_submit=True):
    t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
    g_sel = st.selectbox("GRUPO", grupos_db)
    concepto = st.text_input("CONCEPTO")
    c1, c2 = st.columns(2)
    c_act = c1.number_input("Cuota", 1, 300, 1)
    c_tot = c2.number_input("Total", 1, 300, 1)
    m_input = st.text_input("MONTO (Ej: 1.500,00)", value="0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("PAGO", OPCIONES_PAGO)
    f_fecha = st.date_input("FECHA DE PAGO", datetime.date.today())
    
    if st.form_submit_button("GRABAR"):
        m_final = procesar_monto_input(m_input)
        conn = sqlite3.connect(DB_NAME)
        idx_base = MESES.index(mes_global)
        for i in range(int(c_act), int(c_tot) + 1):
            offset = i - int(c_act)
            mes_target = MESES[(idx_base + offset) % 12]
            lbl_cuota = f"{i}/{int(c_tot)}"
            fecha_v = f_fecha + pd.DateOffset(months=offset)
            conn.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(datetime.date.today()), mes_target, t_sel, g_sel, concepto, lbl_cuota, m_final, mon_sel, f_pago, fecha_v.strftime('%Y-%m-%d')))
        conn.commit(); conn.close(); st.success("Guardado"); st.rerun()

# --- PESTAÑAS ---
tab_dash, tab_conf = st.tabs(["📊 PLANILLA", "⚙️ CONFIGURACIÓN"])

with tab_dash:
    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    
    df_mes = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_mes.empty:
        # --- MÉTRICAS ---
        ing_ars = df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GANANCIA")]['monto'].sum()
        gas_ars = df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        res_ars = ing_ars - gas_ars
        
        ing_usd = df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GANANCIA")]['monto'].sum()
        gas_usd = df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        res_usd = ing_usd - gas_usd
        
        patrimonio_total_ars = res_ars + (res_usd * dolar_val)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("RESULTADO MES (ARS)", formato_moneda_visual(res_ars, "ARS"))
        c2.metric("RESULTADO MES (USD)", formato_moneda_visual(res_usd, "USD"))
        c3.metric("RESULTADO TOTAL (EN PESOS)", formato_moneda_visual(patrimonio_total_ars, "ARS"), help="Suma de tus Pesos + tus Dólares convertidos al Blue")
        
        st.divider()
        
        # --- GRÁFICOS ---
        df_mes_graf = df_mes.copy()
        df_mes_graf['m_ars_v'] = df_mes_graf.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        
        col_pie, col_ars, col_usd = st.columns(3)
        with col_pie:
            st.caption("Distribución de Gastos")
            if not df_mes_graf[df_mes_graf['tipo']=="GASTO"].empty:
                st.plotly_chart(px.pie(df_mes_graf[df_mes_graf['tipo']=="GASTO"], values='m_ars_v', names='grupo', hole=0.4), use_container_width=True)
        with col_ars:
            st.caption("Flujo ARS")
            if not df_mes_graf[df_mes_graf['moneda']=="ARS"].empty:
                st.plotly_chart(px.bar(df_mes_graf[df_mes_graf['moneda']=="ARS"].groupby('tipo')['monto'].sum().reset_index(), x='tipo', y='monto', color='tipo', color_discrete_map={"GANANCIA":"#28a745","GASTO":"#dc3545"}), use_container_width=True)
        with col_usd:
            st.caption("Flujo USD")
            if not df_mes_graf[df_mes_graf['moneda']=="USD"].empty:
                st.plotly_chart(px.bar(df_mes_graf[df_mes_graf['moneda']=="USD"].groupby('tipo')['monto'].sum().reset_index(), x='tipo', y='monto', color='tipo', color_discrete_map={"GANANCIA":"#28a745","GASTO":"#dc3545"}), use_container_width=True)

        st.divider()

        # --- TABLA JERÁRQUICA ---
        df_view = df_mes.copy()
        df_view['monto_visual'] = df_view.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        df_view = df_view.sort_values(by=["grupo", "tipo_gasto"])
        
        columnas_ordenadas = ["tipo_gasto", "monto_visual", "cuota", "tipo", "forma_pago", "fecha_pago"]
        
        column_cfg = {
            "id": None, "mes": None, "fecha": None, "monto": None, "moneda": None,
            "grupo": "GRUPO",
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"),
            "monto_visual": st.column_config.TextColumn("MONTO", width="medium"),
            "cuota": st.column_config.TextColumn("CUOTA", width="small"),
            "tipo": st.column_config.TextColumn("TIPO", width="small"),
            "forma_pago": st.column_config.TextColumn("FORMA DE PAGO", width="medium"),
            "fecha_pago": st.column_config.DateColumn("FECHA DE PAGO", format="DD/MM/YYYY", width="medium"),
        }
        
        selection = st.dataframe(
            df_view.set_index("grupo")[columnas_ordenadas],
            column_config=column_cfg,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # --- EDICIÓN ---
        if selection["selection"]["rows"]:
            st.divider()
            st.markdown("##### ✏️ EDITAR SELECCIÓN")
            try:
                idx_sel = selection["selection"]["rows"][0]
                row_data = df_view.iloc[idx_sel]
                id_mov = int(row_data['id'])
                
                with st.form(key="form_edit"):
                    c_e1, c_e2, c_e3 = st.columns([1, 2, 1])
                    new_grupo = c_e1.selectbox("Grupo", grupos_db, index=grupos_db.index(row_data['grupo']) if row_data['grupo'] in grupos_db else 0)
                    new_concepto = c_e2.text_input("Concepto", value=row_data['tipo_gasto'])
                    val_edit = formato_moneda_visual(row_data['monto'], row_data['moneda']).replace("US$ ", "").replace("$ ", "")
                    new_monto = c_e3.text_input("Monto", value=val_edit)
                    
                    c_e4, c_e5, c_e6 = st.columns(3)
                    new_cuota = c_e4.text_input("Cuota", value=row_data['cuota'])
                    new_moneda = c_e5.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(row_data['moneda']))
                    new_pago = c_e6.selectbox("Forma de Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(row_data['forma_pago']) if row_data['forma_pago'] in OPCIONES_PAGO else 0)
                    
                    c_e7 = st.columns(1)[0]
                    try: f_val = pd.to_datetime(row_data['fecha_pago']).date()
                    except: f_val = datetime.date.today()
                    new_fecha = c_e7.date_input("Fecha de Pago", value=f_val)
                    
                    col_b1, col_b2 = st.columns([1, 1])
                    if col_b1.form_submit_button("💾 ACTUALIZAR"):
                        final_monto = procesar_monto_input(new_monto)
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute("""UPDATE movimientos SET grupo=?, tipo_gasto=?, monto=?, cuota=?, moneda=?, forma_pago=?, fecha_pago=? WHERE id=?""", 
                                     (new_grupo, new_concepto, final_monto, new_cuota, new_moneda, new_pago, str(new_fecha), id_mov))
                        conn.commit(); conn.close(); st.success("Actualizado"); st.rerun()
                    
                    if col_b2.form_submit_button("❌ ELIMINAR", type="primary"):
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute("DELETE FROM movimientos WHERE id=?", (id_mov,))
                        conn.commit(); conn.close(); st.warning("Eliminado"); st.rerun()
            except Exception as e: st.error(f"Error selección: {e}")
    else: st.info("Sin movimientos.")

with tab_conf:
    st.subheader("⚙️ ADMINISTRACIÓN")
    st.write("#### 🏷️ GRUPOS")
    c1, c2, c3 = st.columns(3)
    with c1:
        ng = st.text_input("Crear Grupo").upper()
        if st.button("➕ Crear"):
            conn = sqlite3.connect(DB_NAME); conn.execute("INSERT OR IGNORE INTO grupos VALUES (?)", (ng,)); conn.commit(); conn.close(); st.rerun()
    with c2:
        if grupos_db:
            g_ren = st.selectbox("Renombrar", grupos_db)
            g_new = st.text_input("Nuevo Nombre").upper()
            if st.button("✏️ Cambiar"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("UPDATE grupos SET nombre=? WHERE nombre=?",(g_new, g_ren))
                conn.execute("UPDATE movimientos SET grupo=? WHERE grupo=?",(g_new, g_ren))
                conn.commit(); conn.close(); st.rerun()
    with c3:
        if grupos_db:
            g_del = st.selectbox("Eliminar", grupos_db)
            if st.button("🗑️ Borrar"):
                conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM grupos WHERE nombre=?", (g_del,)); conn.commit(); conn.close(); st.rerun()

    st.divider()
    st.write("#### 👯 CLONAR MES")
    cc1, cc2, cc3 = st.columns(3)
    with cc1: m_src = st.selectbox("Origen", MESES, key="s")
    with cc2: m_dst = st.selectbox("Destino", ["TODO EL AÑO"] + MESES, key="d")
    with cc3:
        st.write("")
        if st.button("🚀 EJECUTAR"):
            conn = sqlite3.connect(DB_NAME)
            src = pd.read_sql(f"SELECT * FROM movimientos WHERE mes = '{m_src}'", conn)
            if not src.empty:
                targets = MESES if m_dst == "TODO EL AÑO" else [m_dst]
                for t in targets:
                    if t == m_src: continue
                    conn.execute(f"DELETE FROM movimientos WHERE mes = '{t}'")
                    for _, r in src.iterrows():
                        conn.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (str(datetime.date.today()), t, r['tipo'], r['grupo'], r['tipo_gasto'], r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
                conn.commit(); st.success("Hecho"); st.rerun()
            conn.close()
    st.divider()
    with open(DB_NAME, 'rb') as f: st.download_button("💾 RESPALDO", f, "backup.db")