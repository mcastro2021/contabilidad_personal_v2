import streamlit as st
import pandas as pd
import psycopg2
import os
import requests
import datetime
import plotly.express as px
import plotly.graph_objects as go
import hashlib
from streamlit_lottie import st_lottie
from dotenv import load_dotenv
from sklearn.linear_model import LinearRegression 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import calendar
import logging

# --- IMPORTACIÓN SEGURA DE IA ---
try:
    import google.generativeai as genai
    HAS_AI = True
except ImportError:
    HAS_AI = False

# --- CONFIGURACIÓN DE LOGGING ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- CARGAR VARIABLES ---
load_dotenv()

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="CONTABILIDAD PERSONAL V5 (IA)", layout="wide")

# --- COLORES GLOBALES ---
COLOR_MAP = {
    "GANANCIA": "#28a745",  # Verde
    "GASTO": "#dc3545"      # Rojo
}

# --- EMAIL NOTIFICACIONES ---
def enviar_notificacion(asunto, mensaje):
    try:
        sender_email = os.environ.get("EMAIL_SENDER")
        sender_password = os.environ.get("EMAIL_PASSWORD")
        receiver_email = os.environ.get("EMAIL_RECEIVER")

        if not all([sender_email, sender_password, receiver_email]): return 

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = f"🔔 FINANZAS V5: {asunto}"
        msg.attach(MIMEText(mensaje, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        logger.info(f"Email enviado: {asunto}")
    except Exception as e: 
        logger.error(f"Fallo envío email: {e}")

# --- GENERADOR DE MESES ---
def generar_lista_meses(start_year=2026, end_year=2035):
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    return [f"{m} {a}" for a in range(start_year, end_year + 1) for m in meses]

LISTA_MESES_LARGA = generar_lista_meses()
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]
SMVM_BASE_2026 = {"Enero 2026": 341000.0, "Febrero 2026": 346800.0, "Marzo 2026": 352400.0, "Abril 2026": 357800.0, "Mayo 2026": 363000.0, "Junio 2026": 367800.0, "Julio 2026": 372400.0, "Agosto 2026": 376600.0}

# --- FUNCIONES AUXILIARES ---
def load_lottieurl(url):
    try: return requests.get(url, timeout=3).json()
    except: return None

LOTTIE_FINANCE = "https://lottie.host/02a55953-2736-4763-b183-116515b81045/L1O1fW89yB.json" 

def make_hashes(p): return hashlib.sha256(str.encode(p)).hexdigest()
def check_hashes(p, h): return make_hashes(p) == h

def formato_moneda_visual(valor, moneda):
    if valor is None or pd.isna(valor): return ""
    try: return f"{'US$ ' if moneda == 'USD' else '$ '}{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

def procesar_monto_input(t):
    if not t: return 0.0
    try: return float(str(t).strip().replace("$","").replace("US","").replace(" ","").replace(".","").replace(",", ".")) if not isinstance(t, (int, float)) else float(t)
    except: return 0.0

# --- NUEVA FUNCIÓN: SISTEMA DE ALERTAS ---
def generar_alertas(df):
    hoy = datetime.date.today()
    limite = hoy + datetime.timedelta(days=5) # 5 días de aviso
    mensajes = []
    
    if df.empty: return mensajes

    # 1. Buscar Pagos Pendientes (Gastos no pagados)
    pendientes = df[(df['tipo'] == 'GASTO') & (df['pagado'] == False)].copy()
    for i, r in pendientes.iterrows():
        try:
            f_pago = pd.to_datetime(r['fecha_pago']).date()
            # Si ya pasó la fecha
            if f_pago < hoy:
                mensajes.append(f"🚨 **VENCIDO:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])}) - Venció el {f_pago.strftime('%d/%m')}")
            # Si vence en los próximos 5 días
            elif hoy <= f_pago <= limite:
                dias_restantes = (f_pago - hoy).days
                txt_dia = "HOY" if dias_restantes == 0 else f"en {dias_restantes} días"
                mensajes.append(f"⚠️ **Vence {txt_dia}:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])})")
        except: pass

    # 2. Buscar Cobros Cercanos (Sueldo/Ingresos)
    # Buscamos palabras clave en ingresos futuros
    ingresos = df[(df['tipo'] == 'GANANCIA')].copy()
    keywords_sueldo = ['sueldo', 'salario', 'honorarios', 'cobro', 'adelanto', 'quincena']
    
    for i, r in ingresos.iterrows():
        try:
            f_cobro = pd.to_datetime(r['fecha_pago']).date()
            # Chequeamos si es un sueldo por palabra clave
            es_sueldo = any(k in str(r['tipo_gasto']).lower() for k in keywords_sueldo)
            
            if es_sueldo and (hoy <= f_cobro <= limite):
                dias_restantes = (f_cobro - hoy).days
                txt_dia = "HOY" if dias_restantes == 0 else f"en {dias_restantes} días"
                mensajes.append(f"💵 **Cobras {txt_dia}:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])})")
        except: pass
        
    return mensajes

# --- BASE DE DATOS ---
def get_db_connection():
    try: return psycopg2.connect(os.environ.get('DATABASE_URL'))
    except Exception as e: 
        logger.critical(f"DB Connection Error: {e}")
        st.error("Error de conexión a Base de Datos"); st.stop()

def init_db():
    try:
        conn = get_db_connection(); c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS movimientos (id SERIAL PRIMARY KEY, fecha TEXT, mes TEXT, tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT, forma_pago TEXT, fecha_pago TEXT)''')
        for col in ["pagado BOOLEAN DEFAULT FALSE", "contrato TEXT DEFAULT ''"]:
            try: c.execute(f"ALTER TABLE movimientos ADD COLUMN {col}"); conn.commit()
            except: conn.rollback()
        c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS deudas (id SERIAL PRIMARY KEY, nombre_deuda TEXT, monto_total REAL, moneda TEXT, fecha_inicio TEXT, estado TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS inversiones (id SERIAL PRIMARY KEY, tipo TEXT, entidad TEXT, monto_inicial REAL, tna REAL, fecha_inicio TEXT, plazo_dias INTEGER, estado TEXT)''')
        c.execute("SELECT count(*) FROM grupos")
        if c.fetchone()[0] == 0: c.executemany("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",), ("DEUDAS",)])
        c.execute("SELECT count(*) FROM users")
        if c.fetchone()[0] == 0: c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", make_hashes("admin123")))
        conn.commit(); conn.close()
    except Exception as e: logger.critical(f"Init DB Error: {e}")

init_db()

# --- BACKUP SQL ---
def generar_backup_sql():
    try:
        conn = get_db_connection(); c = conn.cursor()
        tablas = ['grupos', 'users', 'deudas', 'movimientos', 'inversiones']
        script = "-- BACKUP CONTABILIDAD V5 --\nTRUNCATE TABLE movimientos, deudas, grupos, users, inversiones RESTART IDENTITY CASCADE;\n\n"
        for t in tablas:
            c.execute(f"SELECT * FROM {t}"); rows = c.fetchall()
            if rows:
                cols = [d[0] for d in c.description]
                for r in rows:
                    vals = [f"'{str(v).replace("'", "''")}'" if isinstance(v, str) else ("TRUE" if v is True else "FALSE" if v is False else ("NULL" if v is None else str(v))) for v in r]
                    script += f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(vals)}) ON CONFLICT DO NOTHING;\n"
        script += "\nSELECT setval('movimientos_id_seq', (SELECT MAX(id) FROM movimientos));\nSELECT setval('deudas_id_seq', (SELECT MAX(id) FROM deudas));\nSELECT setval('inversiones_id_seq', (SELECT MAX(id) FROM inversiones));\n"
        conn.close(); return script
    except Exception as e: return f"-- Error: {e}"

# --- LÓGICA AUTOMÁTICA ---
def calcular_monto_salario_mes(m):
    if m in SMVM_BASE_2026: 
        val = SMVM_BASE_2026[m] * 2.5
        return val * 1.5 if "Junio" in m else val
    if "2026" in m:
        try:
            meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            nom = m.split(" ")[0]
            if nom in meses[8:]: # Sep-Dic
                ini, fin = SMVM_BASE_2026["Enero 2026"], SMVM_BASE_2026["Agosto 2026"]
                prom = (fin - ini) / 7; base = fin + (prom * (meses.index(nom) - 7))
                val = base * 2.5; return val * 1.5 if nom == "Diciembre" else val
        except: pass
    return None

def automatizaciones():
    try:
        conn = get_db_connection(); c = conn.cursor()
        c.execute("SELECT id, mes FROM movimientos WHERE tipo_gasto = 'SALARIO CHICOS'")
        for r in c.fetchall():
            v = calcular_monto_salario_mes(r[1])
            if v: c.execute("UPDATE movimientos SET monto=%s WHERE id=%s", (v, r[0]))
        for i, m in enumerate(LISTA_MESES_LARGA):
            c.execute("UPDATE movimientos SET monto=%s WHERE mes=%s AND tipo_gasto='TERRENO'", (13800.0 * ((1.04) ** i), m))
        conn.commit(); conn.close()
    except: pass

def propagar_cuotas(mes, con, cont, grp, mnt, mon, pag, fec, cuota):
    try:
        if "/" not in cuota: return
        act, tot = map(int, cuota.split('/')); idx = LISTA_MESES_LARGA.index(mes)
        conn = get_db_connection(); c = conn.cursor(); cn = act + 1
        while cn <= tot:
            idx += 1; 
            if idx >= len(LISTA_MESES_LARGA): break
            mf = LISTA_MESES_LARGA[idx]; cf = f"{cn}/{tot}"
            try: fs = (pd.to_datetime(fec) + datetime.timedelta(days=(cn-act)*30)).strftime('%Y-%m-%d')
            except: fs = str(datetime.date.today())
            c.execute("UPDATE movimientos SET cuota=%s, monto=%s, moneda=%s, forma_pago=%s, fecha_pago=%s, contrato=%s WHERE mes=%s AND tipo_gasto=%s AND grupo=%s", (cf, mnt, mon, pag, fs, cont, mf, con, grp))
            if c.rowcount == 0:
                c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,'GASTO',%s,%s,%s,%s,%s,%s,%s,%s,FALSE)", (str(datetime.date.today()), mf, grp, con, cont, cf, mnt, mon, pag, fs))
            cn += 1
        conn.commit(); conn.close()
    except: pass

def actualizar_saldos(mes):
    try:
        conn = get_db_connection(); c = conn.cursor(); idx = LISTA_MESES_LARGA.index(mes)
        for i in range(idx, min(len(LISTA_MESES_LARGA)-1, idx+24)):
            ma, ms = LISTA_MESES_LARGA[i], LISTA_MESES_LARGA[i+1]
            c.execute("SELECT COALESCE(SUM(CASE WHEN tipo='GANANCIA' THEN monto ELSE 0 END),0) - COALESCE(SUM(CASE WHEN tipo='GASTO' THEN monto ELSE 0 END),0) FROM movimientos WHERE mes=%s AND moneda='ARS'", (ma,))
            saldo = c.fetchone()[0] or 0.0
            c.execute("SELECT id FROM movimientos WHERE mes=%s AND tipo_gasto='Ahorro Mes Anterior'", (ms,))
            r = c.fetchone()
            if r: c.execute("UPDATE movimientos SET monto=%s WHERE id=%s", (saldo, r[0]))
            else: c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,'GANANCIA','AHORRO MANUEL','Ahorro Mes Anterior','1/1',%s,'ARS','Automático',%s)", (str(datetime.date.today()), ms, saldo, str(datetime.date.today())))
            conn.commit()
        conn.close()
    except: pass

@st.cache_data(ttl=60)
def get_dolar():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3).json()
        return (float(r['compra']) + float(r['venta'])) / 2, f"(Compra: ${int(r['compra'])} | Venta: ${int(r['venta'])})"
    except: return 1480.0, "(Ref)"

# --- LOGIN ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''

if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESO FINANZAS</h1>", unsafe_allow_html=True)
    lottie = load_lottieurl(LOTTIE_FINANCE) 
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if lottie: st_lottie(lottie, height=150)
        with st.form("login"):
            u = st.text_input("Usuario"); p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                conn = get_db_connection(); c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username=%s AND password=%s", (u, make_hashes(p)))
                if c.fetchall(): 
                    st.session_state['logged_in'] = True; st.session_state['username'] = u; st.rerun()
                else: 
                    st.error("Error"); conn.close()
    st.stop()

# ==========================================
# APP
# ==========================================
dolar_val, dolar_info = get_dolar()
automatizaciones()
conn = get_db_connection()
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
df_all = pd.read_sql("SELECT * FROM movimientos", conn)
conn.close()

with st.sidebar:
    lottie = load_lottieurl(LOTTIE_FINANCE)
    if lottie: st_lottie(lottie, height=100)
    st.write(f"👤 **{st.session_state['username']}**")
    if st.button("Salir"): st.session_state['logged_in'] = False; st.rerun()
    st.divider()

    # --- SELECTOR DE MES GLOBAL ---
    st.header("📅 Configuración")
    mes_global = st.selectbox("Mes de Trabajo:", LISTA_MESES_LARGA)
    
    st.divider()

    # --- FORMULARIO DE CARGA ---
    st.header("📥 Cargar Nuevo")
    with st.form("alta_movimiento"):
        t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
        g_sel = st.selectbox("GRUPO", grupos_db)
        c_con, c_cont = st.columns(2)
        con = c_con.text_input("CONCEPTO"); cont = c_cont.text_input("CUENTA O CONTRATO")
        c1, c2 = st.columns(2); c_act = c1.number_input("Cuota", 1, 300, 1); c_tot = c2.number_input("Total", 1, 300, 1)
        m_inp = st.text_input("MONTO", "0,00"); mon = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
        pag = st.selectbox("PAGO", OPCIONES_PAGO); fec = st.date_input("FECHA", datetime.date(2026, 1, 1))
        ya = st.checkbox("¿Pagado?")
        
        if st.form_submit_button("GRABAR"):
            mf = procesar_monto_input(m_inp); conn = get_db_connection(); c = conn.cursor(); idx = LISTA_MESES_LARGA.index(mes_global)
            if c_tot == 1:
                vc = calcular_monto_salario_mes(mes_global)
                mg = vc if (con.strip().upper() == "SALARIO CHICOS" and vc) else mf
                c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,'',%s,%s,%s,%s,%s)", (str(datetime.date.today()), mes_global, t_sel, g_sel, con, cont, mg, mon, pag, str(fec), ya))
            else:
                for i in range(int(c_act), int(c_tot)+1):
                    off = i - int(c_act)
                    if idx + off < len(LISTA_MESES_LARGA):
                        mt = LISTA_MESES_LARGA[idx + off]; vc = calcular_monto_salario_mes(mt)
                        mg = vc if (con.strip().upper() == "SALARIO CHICOS" and vc) else mf
                        c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()), mt, t_sel, g_sel, con, cont, f"{i}/{c_tot}", mg, mon, pag, (fec + datetime.timedelta(days=30*off)).strftime('%Y-%m-%d'), ya if off==0 else False))
            conn.commit(); conn.close(); actualizar_saldos(mes_global)
            enviar_notificacion("Nuevo", f"{con} ({mf})"); st.success("Guardado"); st.rerun()

    st.divider()

    # --- CHAT IA ---
    with st.expander("🤖 Asistente IA (Chat)", expanded=False):
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            st.warning("Falta API Key")
        elif not HAS_AI:
            st.error("Falta librería IA")
        else:
            try:
                genai.configure(api_key=api_key)
                models_list = []
                try:
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods: models_list.append(m.name)
                except: pass
                
                if not models_list: model_name = 'models/gemini-1.5-flash'
                else:
                    preferidos = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-pro']
                    model_name = next((m for m in preferidos if m in models_list), models_list[0])
                
                st.caption(f"🧠 {model_name.split('/')[-1]}")
                model = genai.GenerativeModel(model_name)
                
                with st.form(key="chat_ia_form"):
                    pregunta = st.text_input("Pregunta sobre tus datos:", key="q_ia_sb")
                    enviado_chat = st.form_submit_button("Enviar")
                    
                    if enviado_chat and pregunta:
                        with st.spinner("Pensando..."):
                            try:
                                df_chat = df_all.copy()
                                info = ", ".join([f"{c} ({t})" for c, t in zip(df_chat.columns, df_chat.dtypes)])
                                prompt = f"""
                                Contexto: Finanzas en Argentina. Moneda: ARS ($).
                                DataFrame `df_chat`: {info}.
                                Usuario: "{pregunta}".
                                
                                Instrucciones OBLIGATORIAS:
                                1. Genera SOLO bloque de código Python. Sin markdown.
                                2. BÚSQUEDA FLEXIBLE: Usa Regex. Ej: 'poll' encuentra 'pollo', 'pollos'. Usa `.str.contains(r'termino', case=False, na=False, regex=True)`. Busca en `tipo_gasto` y `grupo`.
                                3. TOTALES: Suma columna `monto`.
                                4. VARIABLES: `resultado_texto` (str) y `figura_plotly` (px).
                                5. NO print().
                                """
                                resp = model.generate_content(prompt).text.replace("```python", "").replace("```", "").strip()
                                loc = {"df_chat": df_chat, "pd": pd, "px": px, "go": go, "st": st}
                                exec(resp, globals(), loc)
                                
                                if "resultado_texto" in loc: st.info(loc["resultado_texto"])
                                if "figura_plotly" in loc and isinstance(loc["figura_plotly"], go.Figure):
                                    st.plotly_chart(loc["figura_plotly"], use_container_width=True)
                            except Exception as e: st.error(f"Error: {e}")
            except Exception as e: st.error(f"Conexión IA: {e}")

# --- TABS PRINCIPALES ---
st.title("CONTABILIDAD PERSONAL V5")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 DASHBOARD", "💰 INVERSIONES", "🔮 PREDICCIONES", "⚙️ CONFIGURACIÓN", "📉 DEUDAS"])

with tab1:
    # --- SISTEMA DE ALERTAS (NUEVO) ---
    alertas = generar_alertas(df_all)
    if alertas:
        with st.expander(f"🔔 Tienes {len(alertas)} Avisos Importantes", expanded=True):
            for alerta in alertas:
                if "VENCIDO" in alerta: st.error(alerta)
                elif "Cobras" in alerta: st.success(alerta)
                else: st.warning(alerta)
    # ----------------------------------

    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    df_filtrado = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_filtrado.empty:
        # KPI GENERAL
        r_ars = df_filtrado[(df_filtrado['moneda']=="ARS")&(df_filtrado['tipo']=="GANANCIA")]['monto'].sum() - df_filtrado[(df_filtrado['moneda']=="ARS")&(df_filtrado['tipo']=="GASTO")]['monto'].sum()
        r_usd = df_filtrado[(df_filtrado['moneda']=="USD")&(df_filtrado['tipo']=="GANANCIA")]['monto'].sum() - df_filtrado[(df_filtrado['moneda']=="USD")&(df_filtrado['tipo']=="GASTO")]['monto'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("RESULTADO (ARS)", formato_moneda_visual(r_ars, "ARS"))
        c2.metric("RESULTADO (USD)", formato_moneda_visual(r_usd, "USD"))
        c3.metric("PATRIMONIO", formato_moneda_visual(r_ars + (r_usd * dolar_val), "ARS"))
        st.divider()

        # CALENDARIO
        filtro_dia = None
        try:
            mn, an = mes_global.split(" "); av = int(an); mv = {"Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6,"Julio":7,"Agosto":8,"Septiembre":9,"Octubre":10,"Noviembre":11,"Diciembre":12}.get(mn, 1)
            _, nd = calendar.monthrange(av, mv)
            fechas = [datetime.date(av, mv, d) for d in range(1, nd+1)]
            dfc = df_filtrado.copy(); dfc['fd'] = pd.to_datetime(dfc['fecha_pago']).dt.date
            cdata = [{"Dia": f.day, "Sem": int(f.strftime("%U")), "DS": f.weekday(), "M": dfc[dfc['fd']==f]['monto'].sum()} for f in fechas]
            dfcal = pd.DataFrame(cdata); dfcal['SR'] = dfcal['Sem'] - dfcal['Sem'].min()
            
            fig_cal = go.Figure(data=go.Scatter(x=dfcal['DS'], y=dfcal['SR'], text=dfcal['Dia'], mode='markers+text',
                marker=dict(size=45, symbol='square', color=dfcal['M'], colorscale='Greens', showscale=False, line=dict(width=1, color='gray')),
                textfont=dict(color='black', size=12), hovertext=[f"${r.M:,.0f}" for i, r in dfcal.iterrows()]))
            fig_cal.update_layout(title=dict(text=f"📅 {mes_global} (Click para filtrar día)", x=0.5), xaxis=dict(showgrid=False, zeroline=False, tickvals=[0,1,2,3,4,5,6], ticktext=["L","M","M","J","V","S","D"], side='top', range=[-0.5, 6.5]), yaxis=dict(showgrid=False, zeroline=False, autorange="reversed", showticklabels=False), height=350, margin=dict(t=50, b=10), clickmode='event+select', plot_bgcolor='rgba(0,0,0,0)')
            sel_cal = st.plotly_chart(fig_cal, on_select="rerun", selection_mode="points", use_container_width=True)
            if sel_cal and sel_cal["selection"]["points"]:
                filtro_dia = int(sel_cal["selection"]["points"][0]["text"])
                st.info(f"🔎 Filtrando Día: {filtro_dia}")
                df_filtrado = df_filtrado[pd.to_datetime(df_filtrado['fecha_pago']).dt.day == filtro_dia]
        except: pass

        # GRÁFICOS
        df_filtrado['m_ars_v'] = df_filtrado.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        c_g1, c_g2 = st.columns(2)
        filtro_grupo = None
        
        with c_g1:
            st.caption("Distribución de Gastos (Click para filtrar)")
            df_gastos = df_filtrado[df_filtrado['tipo']=="GASTO"]
            if not df_gastos.empty:
                fig_pie = px.pie(df_gastos, values='m_ars_v', names='grupo', hole=0.4)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label', hovertemplate='%{label}: $%{value:,.0f}<br>(%{percent})')
                fig_pie.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
                sel_pie = st.plotly_chart(fig_pie, on_select="rerun", selection_mode="points", use_container_width=True)
                if sel_pie and sel_pie["selection"]["points"]:
                    filtro_grupo = sel_pie["selection"]["points"][0]["label"]
                    st.warning(f"📂 Filtrando por Grupo: {filtro_grupo}")

        with c_g2:
            st.caption("Flujo de Caja (Ingresos vs Egresos)")
            if not df_filtrado.empty:
                df_flow = df_filtrado.groupby(['moneda', 'tipo'])['monto'].sum().reset_index()
                st.plotly_chart(px.bar(df_flow, x='moneda', y='monto', color='tipo', barmode='group', color_discrete_map=COLOR_MAP), use_container_width=True)

        # TABLA
        df_tabla = df_filtrado.copy()
        if filtro_grupo: df_tabla = df_tabla[df_tabla['grupo'] == filtro_grupo]

        df_tabla['monto_vis'] = df_tabla.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        df_tabla['pagado'] = df_tabla['pagado'].fillna(False).astype(bool)
        df_tabla['estado'] = df_tabla['pagado'].apply(lambda x: "✅" if x else "⏳")
        df_tabla['tipo_vis'] = df_tabla['tipo'].apply(lambda x: "🟢 GANANCIA" if x=="GANANCIA" else "🔴 GASTO")
        if 'contrato' not in df_tabla.columns: df_tabla['contrato'] = ""

        cols = ["estado", "tipo_vis", "tipo_gasto", "contrato", "monto_vis", "cuota", "forma_pago", "fecha_pago", "pagado"]
        cfg = {
            "estado": st.column_config.TextColumn("E", width="small"), 
            "tipo_vis": st.column_config.TextColumn("TIPO"),
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"), 
            "contrato": st.column_config.TextColumn("CUENTA/CONTRATO"), 
            "monto_vis": st.column_config.TextColumn("MONTO"), 
            "cuota": st.column_config.TextColumn("CUOTA"), 
            "forma_pago": st.column_config.TextColumn("FORMA DE PAGO"), 
            "fecha_pago": st.column_config.DateColumn("FECHA DE PAGO", format="DD/MM/YYYY"), 
            "pagado": st.column_config.CheckboxColumn("PAGADO")
        }

        st.markdown("---")
        def style_fn(row): return ['background-color: #1c3323' if row['pagado'] else ''] * len(row)
        selected = []
        
        for gt in ["GANANCIA", "GASTO"]:
            dft = df_tabla[df_tabla['tipo'] == gt]
            if not dft.empty:
                st.markdown(f"## {('🟢' if gt=='GANANCIA' else '🔴')} {gt}S")
                for grp in sorted(dft['grupo'].unique()):
                    with st.container():
                        st.subheader(f"📂 {grp}")
                        # ORDENAMIENTO: No Pagados (False) primero, luego fecha
                        dfg = dft[dft['grupo'] == grp].sort_values(by=['pagado', 'fecha_pago'], ascending=[True, True])
                        s = st.dataframe(dfg[cols].style.apply(style_fn, axis=1), column_config=cfg, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"t_{gt}_{grp}")
                        
                        # SUBTOTAL
                        total_grupo = dfg['m_ars_v'].sum()
                        st.markdown(f"**📉 Total {grp}: {formato_moneda_visual(total_grupo, 'ARS')}**")

                        if s.selection.rows:
                            for i in s.selection.rows: selected.append(dfg.iloc[i])
        
        # EDICION
        if len(selected) == 1:
            r = selected[0]; idm = int(r['id'])
            st.markdown(f"### ✏️ Editar: {r['tipo_gasto']}")
            with st.form("edit"):
                c1,c2,c3,c4 = st.columns(4)
                nt = c1.selectbox("Tipo", ["GASTO", "GANANCIA"], index=["GASTO", "GANANCIA"].index(r['tipo']))
                ng = c2.selectbox("Grupo", grupos_db, index=grupos_db.index(r['grupo']) if r['grupo'] in grupos_db else 0)
                nc = c3.text_input("Concepto", value=r['tipo_gasto'])
                nct = c4.text_input("Contrato", value=r['contrato'])
                c5,c6,c7 = st.columns(3)
                nm = c5.text_input("Monto", value=str(r['monto']).replace('.', ','))
                nmo = c6.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(r['moneda']))
                ncu = c7.text_input("Cuota", value=str(r['cuota']))
                c8,c9,c10 = st.columns(3)
                npg = c8.selectbox("Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(r['forma_pago']) if r['forma_pago'] in OPCIONES_PAGO else 0)
                try: fd = pd.to_datetime(r['fecha_pago']).date()
                except: fd = datetime.date.today()
                nf = c9.date_input("Fecha", value=fd)
                npa = c10.checkbox("PAGADO", value=bool(r['pagado']))
                b1, b2 = st.columns(2)
                if b1.form_submit_button("💾 Guardar"):
                    conn = get_db_connection(); c = conn.cursor()
                    c.execute("UPDATE movimientos SET tipo=%s, grupo=%s, tipo_gasto=%s, contrato=%s, monto=%s, moneda=%s, cuota=%s, forma_pago=%s, fecha_pago=%s, pagado=%s WHERE id=%s", (nt, ng, nc, nct, procesar_monto_input(nm), nmo, ncu, npg, str(nf), npa, idm))
                    conn.commit(); conn.close(); actualizar_saldos(mes_global); st.success("Ok"); st.rerun()
                if b2.form_submit_button("❌ Eliminar"):
                    conn = get_db_connection(); c = conn.cursor(); c.execute("DELETE FROM movimientos WHERE id=%s", (idm,)); conn.commit(); conn.close(); actualizar_saldos(mes_global); st.rerun()
        
        elif len(selected) > 1:
            st.warning(f"Seleccionados: {len(selected)}")
            if st.button("🗑️ Eliminar Todo"):
                conn = get_db_connection(); c = conn.cursor()
                c.execute("DELETE FROM movimientos WHERE id IN %s", (tuple([int(x['id']) for x in selected]),))
                conn.commit(); conn.close(); actualizar_saldos(mes_global); st.rerun()

with tab2: # INVERSIONES
    st.header("💰 Inversiones")
    with st.expander("➕ NUEVA", expanded=False):
        with st.form("inv"):
            c1,c2,c3 = st.columns(3); t = c1.selectbox("Tipo", ["Plazo Fijo", "Billetera (FCI)"]); e = c2.text_input("Entidad"); m = c3.text_input("Monto", "0,00")
            c4,c5,c6 = st.columns(3); tn = c4.number_input("TNA %", 0.0, 300.0, 40.0); f = c5.date_input("Inicio", datetime.date.today()); p = c6.number_input("Días", 30, 365, 30)
            if st.form_submit_button("Crear"):
                conn = get_db_connection(); c = conn.cursor(); c.execute("INSERT INTO inversiones (tipo, entidad, monto_inicial, tna, fecha_inicio, plazo_dias, estado) VALUES (%s,%s,%s,%s,%s,%s,'ACTIVA')", (t, e, procesar_monto_input(m), tn, str(f), p))
                conn.commit(); conn.close(); st.rerun()
    
    conn = get_db_connection(); dfi = pd.read_sql("SELECT * FROM inversiones WHERE estado='ACTIVA'", conn); conn.close()
    if not dfi.empty:
        tot = dfi['monto_inicial'].sum(); gan = 0.0
        for i, r in dfi.iterrows():
            dt = max(0, (datetime.date.today() - pd.to_datetime(r['fecha_inicio']).date()).days)
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                if r['tipo'] == "Plazo Fijo":
                    fin = r['monto_inicial'] + (r['monto_inicial']*(r['tna']/100)*(r['plazo_dias']/365))
                    prog = max(0.0, min(dt/r['plazo_dias'], 1.0)) if r['plazo_dias']>0 else 0.0
                    c1.markdown(f"**🏦 {r['entidad']}** (PF)"); c1.progress(prog, f"Día {dt}/{r['plazo_dias']}")
                    k1,k2,k3=c1.columns(3); k1.metric("Inv", formato_moneda_visual(r['monto_inicial'],"ARS")); k2.metric("Cobro", formato_moneda_visual(fin,"ARS")); k3.metric("Vence", (pd.to_datetime(r['fecha_inicio'])+datetime.timedelta(days=r['plazo_dias'])).strftime('%d/%m'))
                    gan += (r['monto_inicial']*(r['tna']/100)*(dt/365))
                else:
                    act = r['monto_inicial'] * ((1 + ((r['tna']/100)/365))**dt)
                    c1.markdown(f"**📱 {r['entidad']}** (FCI)"); k1,k2,k3=c1.columns(3)
                    k1.metric("Capital", formato_moneda_visual(r['monto_inicial'],"ARS")); k2.metric("Hoy", formato_moneda_visual(act,"ARS"), delta=formato_moneda_visual(act-r['monto_inicial'],"ARS")); k3.metric("Días", dt)
                    gan += (act - r['monto_inicial'])
                if c2.button("Fin", key=f"f{r['id']}"): 
                    conn=get_db_connection();c=conn.cursor();c.execute("UPDATE inversiones SET estado='FINALIZADA' WHERE id=%s",(r['id'],));conn.commit();conn.close();st.rerun()
        st.info(f"Capital: {formato_moneda_visual(tot,'ARS')} | Ganancia Est.: {formato_moneda_visual(gan,'ARS')}")

with tab3: # PREDICCIONES
    st.header("🔮 Tendencias y Proyecciones")
    df_base = df_all[df_all['tipo'] == 'GASTO'].copy()
    if not df_base.empty:
        df_base['monto_calc'] = df_base.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        opciones_prediccion = ["TOTAL GENERAL"] + sorted(df_base['grupo'].unique().tolist())
        seleccion = st.selectbox("¿Qué quieres analizar?", opciones_prediccion)
        df_ai = df_base if seleccion == "TOTAL GENERAL" else df_base[df_base['grupo'] == seleccion]
        mapa_meses = {m: i for i, m in enumerate(LISTA_MESES_LARGA)}
        df_ai['mes_idx'] = df_ai['mes'].map(mapa_meses)
        df_tendencia = df_ai.groupby(['mes_idx', 'mes'])['monto_calc'].sum().reset_index().sort_values('mes_idx')

        if len(df_tendencia) >= 2:
            X = df_tendencia['mes_idx'].values.reshape(-1, 1); y = df_tendencia['monto_calc'].values
            model = LinearRegression(); model.fit(X, y)
            siguiente_mes_idx = df_tendencia['mes_idx'].max() + 1
            prediccion = max(0, model.predict([[siguiente_mes_idx]])[0])
            promedio_historico = y.mean(); diferencia = prediccion - promedio_historico
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Promedio Histórico", formato_moneda_visual(promedio_historico, "ARS"))
            c2.metric("Proyección Próximo Mes", formato_moneda_visual(prediccion, "ARS"), delta=formato_moneda_visual(diferencia, "ARS"), delta_color="inverse")
            c3.info(f"Tendencia: **{'📈 Subiendo' if diferencia > 0 else '📉 Bajando'}**")

            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_tendencia['mes'], y=df_tendencia['monto_calc'], name='Gasto Real', marker_color='#6c757d'))
            fig.add_trace(go.Scatter(x=df_tendencia['mes'], y=model.predict(X), mode='lines', name='Tendencia', line=dict(color='#007bff', width=3, dash='dot')))
            nombre_prox = LISTA_MESES_LARGA[siguiente_mes_idx] if siguiente_mes_idx < len(LISTA_MESES_LARGA) else "Próximo"
            fig.add_trace(go.Scatter(x=[nombre_prox], y=[prediccion], mode='markers+text', name='Proyección', marker=dict(color='#28a745', size=15, symbol='star'), text=[formato_moneda_visual(prediccion, "ARS")], textposition="top center"))
            fig.update_layout(title=f"Evolución: {seleccion}", height=400)
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("Faltan datos para predecir.")
    else: st.info("Sin datos.")

with tab4: # CONFIG
    st.header("⚙️ Configuración")
    with st.expander("🔄 REPLICADOR DE GASTOS", expanded=False):
        c1, c2 = st.columns(2); mm = c1.selectbox("Mes Modelo", LISTA_MESES_LARGA)
        conn=get_db_connection(); dfm=pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{mm}' AND tipo='GASTO'", conn); conn.close()
        if not dfm.empty:
            gs = st.multiselect("Gastos a copiar", dfm['tipo_gasto'].unique()); md = st.multiselect("Destino", LISTA_MESES_LARGA)
            if st.button("Replicar"):
                conn=get_db_connection();c=conn.cursor();cnt=0
                for m in md:
                    if m==mm: continue
                    for g in gs:
                        r=dfm[dfm['tipo_gasto']==g].iloc[0]
                        c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,contrato,cuota,monto,moneda,forma_pago,fecha_pago,pagado) VALUES (%s,%s,%s,%s,%s,%s,'1/1',%s,%s,%s,%s,FALSE)", (str(datetime.date.today()),m,r['tipo'],r['grupo'],r['tipo_gasto'],r['contrato'],r['monto'],r['moneda'],r['forma_pago'],str(datetime.date.today())))
                        cnt+=1
                conn.commit();conn.close();st.success(f"{cnt} creados")
    st.divider()
    st.download_button("📦 BACKUP SQL", generar_backup_sql(), "backup.sql")
    c1,c2,c3 = st.columns(3); ms=c1.selectbox("Desde", LISTA_MESES_LARGA); md=c2.selectbox("Hasta", ["TODO"]+LISTA_MESES_LARGA)
    if c3.button("Clonar Mes"):
        conn=get_db_connection();c=conn.cursor();df=pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{ms}'", conn)
        tgs=[m for m in LISTA_MESES_LARGA if m.split(' ')[1]==ms.split(' ')[1]] if md=="TODO" else [md]
        for t in tgs:
            if t==ms: continue
            c.execute("DELETE FROM movimientos WHERE mes=%s",(t,))
            for i,r in df.iterrows(): c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,contrato,cuota,monto,moneda,forma_pago,fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()),t,r['tipo'],r['grupo'],r['tipo_gasto'],r['contrato'],r['cuota'],r['monto'],r['moneda'],r['forma_pago'],r['fecha_pago']))
        conn.commit();conn.close();st.success("Hecho");st.rerun()

with tab5: # DEUDAS
    st.header("📉 Deudas"); c1,c2=st.columns([1,2]); conn=get_db_connection(); c=conn.cursor()
    with c1:
        with st.form("d"):
            n=st.text_input("Nombre"); mt=st.text_input("Total"); mo=st.selectbox("Moneda",["ARS","USD"])
            if st.form_submit_button("Crear"): c.execute("INSERT INTO deudas (nombre_deuda,monto_total,moneda,fecha_inicio,estado) VALUES (%s,%s,%s,%s,'ACTIVA')",(n,procesar_monto_input(mt),mo,str(datetime.date.today()))); conn.commit(); st.rerun()
    with c2:
        dfd=pd.read_sql("SELECT * FROM deudas WHERE estado='ACTIVA'", conn)
        for i,d in dfd.iterrows():
            with st.expander(f"{d['nombre_deuda']} ({formato_moneda_visual(d['monto_total'],d['moneda'])})", expanded=True):
                c.execute("SELECT sum(monto) FROM movimientos WHERE grupo='DEUDAS' AND tipo_gasto LIKE %s", (f"%{d['nombre_deuda']}%",))
                pg=c.fetchone()[0] or 0.0; rs=d['monto_total']-pg
                st.progress(min(pg/d['monto_total'],1.0) if d['monto_total']>0 else 0)
                k1,k2,k3=st.columns(3); k1.metric("Total",d['monto_total']); k2.metric("Pagado",pg); k3.metric("Falta",rs)
                if rs<=0: 
                    st.success("Pagada"); 
                    if st.button("Archivar", key=f"a{d['id']}"): c.execute("UPDATE deudas SET estado='PAGADA' WHERE id=%s",(d['id'],));conn.commit();st.rerun()
                else:
                    c1,c2=st.columns(2); m=c1.text_input("Monto",key=f"m{d['id']}"); p=c2.selectbox("Pago",OPCIONES_PAGO,key=f"p{d['id']}")
                    if st.button("Pagar",key=f"b{d['id']}"): c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,cuota,monto,moneda,forma_pago,fecha_pago,pagado) VALUES (%s,%s,'GASTO','DEUDAS',%s,'',%s,%s,%s,%s,TRUE)",(str(datetime.date.today()),mes_global,f"Pago: {d['nombre_deuda']}",procesar_monto_input(m),d['moneda'],p,str(datetime.date.today())));conn.commit();st.rerun()
                if st.button("Eliminar",key=f"e{d['id']}"): c.execute("DELETE FROM deudas WHERE id=%s",(d['id'],));conn.commit();st.rerun()
    conn.close()