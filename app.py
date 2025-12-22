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
        return True
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

# --- CONEXIÓN A BASE DE DATOS ROBUSTA ---
def get_db_connection():
    # check_same_thread=False es vital para evitar bloqueos en Streamlit
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, mes TEXT, 
                  tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT,
                  forma_pago TEXT, fecha_pago TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')

    # Datos iniciales solo si está vacía
    c.execute("SELECT count(*) FROM grupos")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT OR IGNORE INTO grupos VALUES (?)", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",)])
        
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password) VALUES (?,?)", ("admin", make_hashes("admin123")))

    conn.commit()
    conn.close()

# Inicializamos DB al arrancar
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

# --- LOGIN SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESO FINANZAS</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, make_hashes(p)))
                if c.fetchall():
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.rerun()
                else: st.error("Error de credenciales")
                conn.close()

if not st.session_state['logged_in']:
    login_page()
    st.stop()

# ==========================================
# APP PRINCIPAL
# ==========================================

with st.sidebar:
    st.write(f"👤 **{st.session_state['username']}**")
    if st.button("Salir"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.divider()

dolar_val, dolar_info = get_dolar()

st.title("SMART FINANCE PRO 2026")
mes_global = st.selectbox("📅 MES DE TRABAJO:", MESES)

# Carga de datos FRESCA (Sin caché para ver cambios al instante)
conn = get_db_connection()
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
df_all = pd.read_sql("SELECT * FROM movimientos", conn)
conn.close()

# --- SIDEBAR CARGA ---
st.sidebar.header("📥 CARGAR NUEVO")
with st.sidebar.form("alta"):
    t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
    g_sel = st.selectbox("GRUPO", grupos_db)
    concepto = st.text_input("CONCEPTO")
    c1, c2 = st.columns(2)
    c_act = c1.number_input("Cuota", 1, 300, 1)
    c_tot = c2.number_input("Total", 1, 300, 1)
    m_input = st.text_input("MONTO (Ej: 1.500,00)", "0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("PAGO", OPCIONES_PAGO)
    f_fecha = st.date_input("FECHA PAGO", datetime.date.today())
    
    if st.form_submit_button("GRABAR"):
        m_final = procesar_monto_input(m_input)
        conn = get_db_connection()
        idx_base = MESES.index(mes_global)
        for i in range(int(c_act), int(c_tot)+1):
            offset = i - int(c_act)
            mes_t = MESES[(idx_base + offset)%12]
            cuota = f"{i}/{int(c_tot)}"
            fecha_v = f_fecha + pd.DateOffset(months=offset)
            conn.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(datetime.date.today()), mes_t, t_sel, g_sel, concepto, cuota, m_final, mon_sel, f_pago, fecha_v.strftime('%Y-%m-%d')))
        conn.commit() # COMMIT EXPLICITO
        conn.close()
        st.success("Guardado correctamente"); st.rerun()

# --- PESTAÑAS ---
tab1, tab2 = st.tabs(["📊 DETALLE POR GRUPOS", "⚙️ CONFIGURACIÓN"])

with tab1:
    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    
    df_mes = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_mes.empty:
        # MÉTRICAS
        i_ars = df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GANANCIA")]['monto'].sum()
        g_ars = df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        i_usd = df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GANANCIA")]['monto'].sum()
        g_usd = df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        res_ars = i_ars - g_ars
        res_usd = i_usd - g_usd
        patrimonio = res_ars + (res_usd * dolar_val)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("RESULTADO (ARS)", formato_moneda_visual(res_ars, "ARS"))
        c2.metric("RESULTADO (USD)", formato_moneda_visual(res_usd, "USD"))
        c3.metric("PATRIMONIO TOTAL ($)", formato_moneda_visual(patrimonio, "ARS"))
        
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
            st.caption("Flujo Pesos")
            if not df_mes_graf[df_mes_graf['moneda']=="ARS"].empty:
                st.plotly_chart(px.bar(df_mes_graf[df_mes_graf['moneda']=="ARS"].groupby('tipo')['monto'].sum().reset_index(), 
                                     x='tipo', y='monto', color='tipo', color_discrete_map={"GANANCIA":"#28a745","GASTO":"#dc3545"}), use_container_width=True)
        with col_usd:
            st.caption("Flujo Dólares")
            if not df_mes_graf[df_mes_graf['moneda']=="USD"].empty:
                st.plotly_chart(px.bar(df_mes_graf[df_mes_graf['moneda']=="USD"].groupby('tipo')['monto'].sum().reset_index(), 
                                     x='tipo', y='monto', color='tipo', color_discrete_map={"GANANCIA":"#28a745","GASTO":"#dc3545"}), use_container_width=True)

        st.divider()
        
        # --- VISTA POR SECCIONES (GRUPOS COMO TÍTULOS) ---
        df_view = df_mes.copy()
        df_view['monto_visual'] = df_view.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        
        # Columnas a mostrar (Grupo ya no está porque es el título)
        cols_show = ["tipo_gasto", "monto_visual", "cuota", "tipo", "forma_pago", "fecha_pago"]
        
        col_cfg = {
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"),
            "monto_visual": st.column_config.TextColumn("MONTO", width="medium"),
            "cuota": st.column_config.TextColumn("CUOTA", width="small"),
            "tipo": st.column_config.TextColumn("TIPO", width="small"),
            "forma_pago": st.column_config.TextColumn("FORMA PAGO", width="medium"),
            "fecha_pago": st.column_config.DateColumn("FECHA PAGO", format="DD/MM/YYYY", width="medium"),
        }

        grupos_en_mes = df_view['grupo'].unique()
        grupos_en_mes.sort()
        
        row_to_edit = None 

        if len(grupos_en_mes) > 0:
            for grp in grupos_en_mes:
                # Título del Grupo
                st.markdown(f"### 📂 {grp}")
                
                # Filtrar datos
                df_grp = df_view[df_view['grupo'] == grp]
                
                # Mostrar Tabla
                selection = st.dataframe(
                    df_grp[cols_show], 
                    column_config=col_cfg,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"tbl_{grp}_{mes_global}"
                )
                
                if selection.selection.rows:
                    idx_visual = selection.selection.rows[0]
                    row_to_edit = df_grp.iloc[idx_visual]

            # --- FORMULARIO DE EDICIÓN ---
            if row_to_edit is not None:
                st.divider()
                st.markdown(f"#### ✏️ EDITANDO: {row_to_edit['tipo_gasto']} (Grupo: {row_to_edit['grupo']})")
                
                with st.form("edit_form"):
                    id_mov = int(row_to_edit['id']) # ID persistente
                    
                    ce1, ce2 = st.columns(2)
                    new_g = ce1.selectbox("Grupo", grupos_db, index=grupos_db.index(row_to_edit['grupo']) if row_to_edit['grupo'] in grupos_db else 0)
                    new_c = ce2.text_input("Concepto", value=row_to_edit['tipo_gasto'])
                    
                    ce3, ce4, ce5 = st.columns(3)
                    val_clean = formato_moneda_visual(row_to_edit['monto'], row_to_edit['moneda']).replace("US$ ", "").replace("$ ", "")
                    new_m = ce3.text_input("Monto", value=val_clean)
                    new_mon = ce4.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(row_to_edit['moneda']))
                    
                    try: f_dt = pd.to_datetime(row_to_edit['fecha_pago']).date()
                    except: f_dt = datetime.date.today()
                    new_f = ce5.date_input("Fecha Pago", value=f_dt)
                    
                    b1, b2 = st.columns([1, 1])
                    if b1.form_submit_button("💾 GUARDAR CAMBIOS"):
                        m_f = procesar_monto_input(new_m)
                        conn = get_db_connection()
                        conn.execute("UPDATE movimientos SET grupo=?, tipo_gasto=?, monto=?, moneda=?, fecha_pago=? WHERE id=?",
                                     (new_g, new_c, m_f, new_mon, str(new_f), id_mov))
                        conn.commit() # Commit inmediato
                        conn.close()
                        st.success("Actualizado"); st.rerun()
                        
                    if b2.form_submit_button("❌ ELIMINAR", type="primary"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM movimientos WHERE id=?", (id_mov,))
                        conn.commit() # Commit inmediato
                        conn.close()
                        st.warning("Eliminado"); st.rerun()
        else:
            st.info("No hay movimientos cargados en este mes.")

with tab2:
    st.header("⚙️ Configuración")
    
    with st.expander("🏷️ GESTIONAR GRUPOS"):
        c1, c2 = st.columns(2)
        with c1:
            n_g = st.text_input("Nuevo Grupo").upper()
            if st.button("Crear Grupo"):
                conn = get_db_connection()
                conn.execute("INSERT OR IGNORE INTO grupos VALUES (?)", (n_g,))
                conn.commit(); conn.close(); st.rerun()
        with c2:
            d_g = st.selectbox("Eliminar Grupo", grupos_db)
            if st.button("Eliminar"):
                conn = get_db_connection()
                conn.execute("DELETE FROM grupos WHERE nombre=?", (d_g,))
                conn.commit(); conn.close(); st.rerun()

    with st.expander("🔐 USUARIOS"):
        u_new = st.text_input("Nuevo Usuario")
        p_new = st.text_input("Nueva Contraseña", type="password")
        if st.button("Crear Usuario"):
            conn = get_db_connection()
            try:
                conn.execute("INSERT INTO users VALUES (?,?)", (u_new, make_hashes(p_new)))
                conn.commit(); st.success("Creado")
            except: st.error("Ya existe")
            finally: conn.close()
            
    with st.expander("🔑 CAMBIAR MI CONTRASEÑA"):
        curr = st.text_input("Actual", type="password")
        n1 = st.text_input("Nueva", type="password")
        n2 = st.text_input("Repetir", type="password")
        if st.button("Cambiar"):
            conn = get_db_connection()
            c = conn.cursor()
            curr_hash = make_hashes(curr)
            user = st.session_state['username']
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (user, curr_hash))
            if c.fetchone():
                if n1 == n2:
                    c.execute("UPDATE users SET password=? WHERE username=?", (make_hashes(n1), user))
                    conn.commit(); st.success("Cambiada! Reingresa."); st.session_state['logged_in']=False; st.rerun()
                else: st.error("No coinciden")
            else: st.error("Contraseña actual incorrecta")
            conn.close()

    st.divider()
    
    st.write("#### 👯 CLONADOR")
    c1, c2, c3 = st.columns(3)
    m_src = c1.selectbox("Desde", MESES)
    m_dst = c2.selectbox("Hasta", ["TODO EL AÑO"]+MESES)
    if c3.button("🚀 CLONAR"):
        conn = get_db_connection()
        src = pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{m_src}'", conn)
        if not src.empty:
            targets = MESES if m_dst == "TODO EL AÑO" else [m_dst]
            for t in targets:
                if t == m_src: continue
                conn.execute(f"DELETE FROM movimientos WHERE mes='{t}'")
                for _, r in src.iterrows():
                    conn.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (str(datetime.date.today()), t, r['tipo'], r['grupo'], r['tipo_gasto'], r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
            conn.commit(); st.success("Clonado!"); st.rerun()
        conn.close()
        
    st.divider()
    with open(DB_NAME, 'rb') as f: st.download_button("💾 BACKUP DB", f, "backup.db")