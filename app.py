import streamlit as st
import pandas as pd
import psycopg2
import os
import sqlite3  # <--- ESTA ERA LA LÍNEA QUE FALTABA
import requests
import datetime
import plotly.express as px
import plotly.graph_objects as go
import hashlib
from streamlit_lottie import st_lottie
import tempfile
from dotenv import load_dotenv
import numpy as np
from sklearn.linear_model import LinearRegression 

# --- CARGAR VARIABLES ---
load_dotenv()

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SMART FINANCE PRO", layout="wide")

# --- FUNCIONES AUXILIARES ---
def load_lottieurl(url):
    try:
        r = requests.get(url)
        if r.status_code != 200: return None
        return r.json()
    except: return None

LOTTIE_FINANCE = "https://lottie.host/02a55953-2736-4763-b183-116515b81045/L1O1fW89yB.json" 
LOTTIE_LOGIN = "https://lottie.host/93291880-990e-473d-82f5-b6574c831168/v2x2QkL6r4.json"
LOTTIE_AI = "https://lottie.host/8078f4a1-0e77-49f3-8027-4638a1670985/9F7o7r2X0q.json"

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

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
def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        st.error("⚠️ Error: No se encontró DATABASE_URL.")
        st.stop()
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        st.error(f"Error DB: {e}")
        st.stop()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                 (id SERIAL PRIMARY KEY, fecha TEXT, mes TEXT, 
                  tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT,
                  forma_pago TEXT, fecha_pago TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    
    # Datos semilla
    c.execute("SELECT count(*) FROM grupos")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",)])
    
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", make_hashes("admin123")))
    
    conn.commit()
    conn.close()

init_db()

# --- CONSTANTES ---
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]

@st.cache_data(ttl=60)
def get_dolar():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3).json()
        return (float(r['compra']) + float(r['venta'])) / 2, f"(Venta: ${int(r['venta'])})"
    except: return 1480.0, "(Ref)"

# --- LOGIN ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESO FINANZAS</h1>", unsafe_allow_html=True)
    lottie_login = load_lottieurl(LOTTIE_LOGIN)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if lottie_login: st_lottie(lottie_login, height=150, key="login_anim")
        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username=%s AND password=%s", (u, make_hashes(p)))
                if c.fetchall():
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.rerun()
                else: st.error("Credenciales incorrectas")
                conn.close()

if not st.session_state['logged_in']:
    login_page()
    st.stop()

# ==========================================
# APP PRINCIPAL
# ==========================================

with st.sidebar:
    lottie_fin = load_lottieurl(LOTTIE_FINANCE)
    if lottie_fin: st_lottie(lottie_fin, height=100, key="sidebar_anim")
    st.write(f"👤 **{st.session_state['username']}**")
    st.caption("Conexión Segura ✅")
    if st.button("Salir"):
        st.session_state['logged_in'] = False
        st.rerun()
    st.divider()

dolar_val, dolar_info = get_dolar()

st.title("SMART FINANCE PRO")
mes_global = st.selectbox("📅 MES DE TRABAJO:", MESES)

conn = get_db_connection()
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
df_all = pd.read_sql("SELECT * FROM movimientos", conn)
conn.close()

# --- CARGA DATOS ---
st.sidebar.header("📥 CARGAR NUEVO")
with st.sidebar.form("alta"):
    t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
    g_sel = st.selectbox("GRUPO", grupos_db)
    concepto = st.text_input("CONCEPTO")
    c1, c2 = st.columns(2)
    c_act = c1.number_input("Cuota", 1, 300, 1)
    c_tot = c2.number_input("Total", 1, 300, 1)
    m_input = st.text_input("MONTO", "0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("PAGO", OPCIONES_PAGO)
    f_fecha = st.date_input("FECHA PAGO", datetime.date.today())
    
    if st.form_submit_button("GRABAR"):
        m_final = procesar_monto_input(m_input)
        conn = get_db_connection()
        c = conn.cursor()
        idx_base = MESES.index(mes_global)
        for i in range(int(c_act), int(c_tot)+1):
            offset = i - int(c_act)
            mes_t = MESES[(idx_base + offset)%12]
            cuota = f"{i}/{int(c_tot)}"
            fecha_v = f_fecha + pd.DateOffset(months=offset)
            c.execute("""INSERT INTO movimientos 
                (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(datetime.date.today()), mes_t, t_sel, g_sel, concepto, cuota, m_final, mon_sel, f_pago, fecha_v.strftime('%Y-%m-%d')))
        conn.commit(); conn.close()
        st.balloons(); st.success("Guardado"); st.rerun()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📊 DASHBOARD", "🔮 PREDICCIONES IA", "⚙️ CONFIGURACIÓN"])

with tab1:
    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    
    df_mes = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_mes.empty:
        # KPI Calculation
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

        # GRAFICOS
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

        st.markdown("---") 
        
        # TABLAS JERARQUICAS
        df_view = df_mes.copy()
        df_view['monto_visual'] = df_view.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        cols_show = ["tipo_gasto", "monto_visual", "cuota", "forma_pago", "fecha_pago"]
        col_cfg = {
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"),
            "monto_visual": st.column_config.TextColumn("MONTO", width="medium"),
            "cuota": st.column_config.TextColumn("CUOTA", width="small"),
            "forma_pago": st.column_config.TextColumn("FORMA PAGO", width="medium"),
            "fecha_pago": st.column_config.DateColumn("FECHA PAGO", format="DD/MM/YYYY", width="medium"),
        }

        row_to_edit = None 

        for gran_tipo in ["GANANCIA", "GASTO"]:
            df_tipo = df_view[df_view['tipo'] == gran_tipo]
            if not df_tipo.empty:
                color = "🟢" if gran_tipo == "GANANCIA" else "🔴"
                plural = "GANANCIAS" if gran_tipo == "GANANCIA" else "GASTOS"
                st.markdown(f"## {color} {plural}")
                grupos_en_tipo = df_tipo['grupo'].unique()
                grupos_en_tipo.sort()
                for grp in grupos_en_tipo:
                    with st.container():
                        st.subheader(f"📂 {grp}")
                        df_grp = df_tipo[df_tipo['grupo'] == grp]
                        selection = st.dataframe(df_grp[cols_show], column_config=col_cfg, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"tbl_{gran_tipo}_{grp}_{mes_global}")
                        if selection.selection.rows: row_to_edit = df_grp.iloc[selection.selection.rows[0]]
                st.divider()

        if row_to_edit is not None:
            st.markdown(f"### ✏️ EDITANDO: {row_to_edit['tipo_gasto']}")
            with st.form("edit_form"):
                id_mov = int(row_to_edit['id']) 
                c_e1, c_e2, c_e3 = st.columns(3)
                new_tipo = c_e1.selectbox("Tipo", ["GASTO", "GANANCIA"], index=["GASTO", "GANANCIA"].index(row_to_edit['tipo']))
                new_g = c_e2.selectbox("Grupo", grupos_db, index=grupos_db.index(row_to_edit['grupo']) if row_to_edit['grupo'] in grupos_db else 0)
                new_c = c_e3.text_input("Concepto", value=row_to_edit['tipo_gasto'])
                c_e4, c_e5, c_e6 = st.columns(3)
                val_clean = formato_moneda_visual(row_to_edit['monto'], row_to_edit['moneda']).replace("US$ ", "").replace("$ ", "")
                new_m = c_e4.text_input("Monto", value=val_clean)
                new_mon = c_e5.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(row_to_edit['moneda']))
                new_cuota = c_e6.text_input("Cuota", value=str(row_to_edit['cuota'])) 
                c_e7, c_e8 = st.columns(2)
                new_pago = c_e7.selectbox("Forma Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(row_to_edit['forma_pago']) if row_to_edit['forma_pago'] in OPCIONES_PAGO else 0)
                try: f_dt = pd.to_datetime(row_to_edit['fecha_pago']).date()
                except: f_dt = datetime.date.today()
                new_f = c_e8.date_input("Fecha Pago", value=f_dt)
                
                b1, b2 = st.columns([1, 1])
                conn = get_db_connection(); c = conn.cursor()
                if b1.form_submit_button("💾 GUARDAR"):
                    m_f = procesar_monto_input(new_m)
                    c.execute("UPDATE movimientos SET tipo=%s, grupo=%s, tipo_gasto=%s, monto=%s, moneda=%s, cuota=%s, forma_pago=%s, fecha_pago=%s WHERE id=%s", (new_tipo, new_g, new_c, m_f, new_mon, new_cuota, new_pago, str(new_f), id_mov))
                    conn.commit(); conn.close(); st.success("Editado"); st.rerun()
                if b2.form_submit_button("❌ ELIMINAR", type="primary"):
                    c.execute("DELETE FROM movimientos WHERE id=%s", (id_mov,)); conn.commit(); conn.close(); st.warning("Eliminado"); st.rerun()
    else: st.info("Sin datos.")

with tab2: # IA
    c1, c2 = st.columns([1,3])
    with c1:
        lottie_ai = load_lottieurl(LOTTIE_AI)
        if lottie_ai: st_lottie(lottie_ai, height=150)
    with c2:
        st.header("🧠 Inteligencia Artificial Financiera")
        st.caption("Análisis predictivo de tus gastos futuros basado en tu historial (Regresión Lineal).")

    # 1. PREPARACIÓN DE DATOS PARA IA
    df_ai = df_all[df_all['tipo'] == 'GASTO'].copy()
    
    if len(df_ai) > 0:
        df_ai['monto_normalizado'] = df_ai.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        mapa_meses = {m: i+1 for i, m in enumerate(MESES)}
        df_ai['mes_num'] = df_ai['mes'].map(mapa_meses)
        df_monthly = df_ai.groupby('mes_num')['monto_normalizado'].sum().reset_index().sort_values('mes_num')
        
        if len(df_monthly) >= 2:
            # 2. ENTRENAMIENTO
            X = df_monthly['mes_num'].values.reshape(-1, 1)
            y = df_monthly['monto_normalizado'].values
            
            model = LinearRegression()
            model.fit(X, y)
            
            # 3. PREDICCIÓN
            proximo_mes_num = df_monthly['mes_num'].max() + 1
            if proximo_mes_num > 12: proximo_mes_num = 1
            
            prediccion_futura = model.predict([[proximo_mes_num]])[0]
            nombre_proximo_mes = MESES[proximo_mes_num - 1] if proximo_mes_num <= 12 else "Próximo Ciclo"
            
            # 4. VISUALIZACIÓN
            col_kpi1, col_kpi2 = st.columns(2)
            col_kpi1.metric(f"Gasto Estimado {nombre_proximo_mes}", formato_moneda_visual(prediccion_futura, "ARS"), 
                            delta=f"{((prediccion_futura - y[-1])/y[-1])*100:.1f}% vs mes anterior", delta_color="inverse")
            
            col_kpi2.info("El modelo analiza la tendencia de tus meses anteriores para proyectar el siguiente.")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[MESES[i-1] for i in df_monthly['mes_num']], y=df_monthly['monto_normalizado'], mode='lines+markers', name='Gasto Real', line=dict(color='#ff4b4b')))
            y_pred = model.predict(X)
            fig.add_trace(go.Scatter(x=[MESES[i-1] for i in df_monthly['mes_num']], y=y_pred, mode='lines', name='Tendencia IA', line=dict(dash='dot', color='gray')))
            fig.add_trace(go.Scatter(x=[nombre_proximo_mes], y=[prediccion_futura], mode='markers', name='Predicción', marker=dict(size=12, color='#00cc96', symbol='star')))
            fig.update_layout(title="Proyección de Gastos", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ Necesitas datos de al menos 2 meses distintos para que la IA pueda detectar tendencias.")
    else:
        st.info("Aún no tienes gastos registrados para analizar.")

with tab3: # CONFIGURACION
    st.header("⚙️ Configuración")
    
    st.markdown("### 📤 MIGRACIÓN DE DATOS")
    archivo_db = st.file_uploader("Sube tu archivo .db", type=["db", "sqlite", "sqlite3"])
    if archivo_db and st.button("🔄 INICIAR MIGRACIÓN"):
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(archivo_db.getvalue()); tmp_path = tmp_file.name
            
            # AQUÍ ES DONDE NECESITAMOS sqlite3
            conn_old = sqlite3.connect(tmp_path)
            df_old = pd.read_sql("SELECT * FROM movimientos", conn_old)
            conn_old.close()
            
            conn_new = get_db_connection(); c_new = conn_new.cursor()
            count = 0
            for _, row in df_old.iterrows():
                c_new.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (row['fecha'], row['mes'], row['tipo'], row['grupo'], row['tipo_gasto'], row['cuota'], row['monto'], row['moneda'], row['forma_pago'], row['fecha_pago']))
                count += 1
            conn_new.commit(); conn_new.close()
            st.success(f"✅ Migrados {count} registros.")
        except Exception as e: st.error(f"Error: {e}")

    st.divider()
    # GESTION GRUPOS
    with st.expander("🏷️ GESTIONAR GRUPOS"):
        c1, c2 = st.columns(2)
        conn = get_db_connection(); c = conn.cursor()
        with c1:
            n_g = st.text_input("Nuevo Grupo").upper()
            if st.button("Crear Grupo"): c.execute("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", (n_g,)); conn.commit(); st.rerun()
        with c2:
            d_g = st.selectbox("Eliminar Grupo", grupos_db)
            if st.button("Eliminar"): c.execute("DELETE FROM grupos WHERE nombre=%s", (d_g,)); conn.commit(); st.rerun()
        conn.close()

    # USUARIOS
    with st.expander("🔐 USUARIOS"):
        u_new = st.text_input("Nuevo Usuario")
        p_new = st.text_input("Nueva Contraseña", type="password")
        if st.button("Crear Usuario"):
            conn = get_db_connection(); c = conn.cursor()
            try: c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", (u_new, make_hashes(p_new))); conn.commit(); st.success("Creado")
            except: st.error("Error al crear")
            finally: conn.close()

    # CAMBIAR PASS
    with st.expander("🔑 CAMBIAR MI CONTRASEÑA"):
        curr = st.text_input("Actual", type="password")
        n1 = st.text_input("Nueva", type="password")
        n2 = st.text_input("Repetir", type="password")
        if st.button("Cambiar"):
            conn = get_db_connection(); c = conn.cursor()
            user = st.session_state['username']
            c.execute("SELECT * FROM users WHERE username=%s AND password=%s", (user, make_hashes(curr)))
            if c.fetchone():
                if n1 == n2: c.execute("UPDATE users SET password=%s WHERE username=%s", (make_hashes(n1), user)); conn.commit(); st.success("Cambiada!"); st.session_state['logged_in']=False; st.rerun()
                else: st.error("No coinciden")
            else: st.error("Incorrecta")
            conn.close()
    
    st.divider()
    # CLONADOR
    c1, c2, c3 = st.columns(3)
    m_src = c1.selectbox("Desde", MESES)
    m_dst = c2.selectbox("Hasta", ["TODO EL AÑO"]+MESES)
    if c3.button("🚀 CLONAR"):
        conn = get_db_connection(); c = conn.cursor()
        src = pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{m_src}'", conn)
        if not src.empty:
            targets = MESES if m_dst == "TODO EL AÑO" else [m_dst]
            for t in targets:
                if t == m_src: continue
                c.execute("DELETE FROM movimientos WHERE mes=%s", (t,))
                for _, r in src.iterrows():
                    c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()), t, r['tipo'], r['grupo'], r['tipo_gasto'], r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
            conn.commit(); st.success("Clonado!"); st.rerun()
        conn.close()