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
import numpy as np
from sklearn.linear_model import LinearRegression 
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import io
import sqlite3
import tempfile
import calendar

# --- CARGAR VARIABLES ---
load_dotenv()

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="CONTABILIDAD PERSONAL V3", layout="wide")

# --- EMAIL NOTIFICACIONES ---
def enviar_notificacion(asunto, mensaje):
    try:
        sender_email = os.environ.get("EMAIL_SENDER")
        sender_password = os.environ.get("EMAIL_PASSWORD")
        receiver_email = os.environ.get("EMAIL_RECEIVER")

        if not all([sender_email, sender_password, receiver_email]): return 

        msg = MIMEMultipart()
        msg['From'] = sender_email; msg['To'] = receiver_email; msg['Subject'] = f"🔔 CONTABILIDAD PERSONAL V3: {asunto}"
        msg.attach(MIMEText(mensaje, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587); server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string()); server.quit()
    except: pass

# --- GENERADOR DE MESES ---
def generar_lista_meses(start_year=2026, end_year=2035):
    meses_base = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    lista = []
    for anio in range(start_year, end_year + 1):
        for mes in meses_base: lista.append(f"{mes} {anio}")
    return lista

LISTA_MESES_LARGA = generar_lista_meses()
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]
SMVM_BASE_2026 = {"Enero 2026": 341000.0, "Febrero 2026": 346800.0, "Marzo 2026": 352400.0, "Abril 2026": 357800.0, "Mayo 2026": 363000.0, "Junio 2026": 367800.0, "Julio 2026": 372400.0, "Agosto 2026": 376600.0}

# --- FUNCIONES AUXILIARES ---
def load_lottieurl(url):
    try: return requests.get(url).json()
    except: return None

LOTTIE_FINANCE = "https://lottie.host/02a55953-2736-4763-b183-116515b81045/L1O1fW89yB.json" 

def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text): return make_hashes(password) == hashed_text

def formato_moneda_visual(valor, moneda):
    if valor is None or pd.isna(valor): return ""
    try:
        num = float(valor)
        s = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{'US$ ' if moneda == 'USD' else '$ '}{s}"
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
    try: return psycopg2.connect(os.environ.get('DATABASE_URL'))
    except Exception as e: st.error(f"Error DB: {e}"); st.stop()

def init_db():
    conn = get_db_connection(); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos (id SERIAL PRIMARY KEY, fecha TEXT, mes TEXT, tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT, forma_pago TEXT, fecha_pago TEXT)''')
    try: c.execute("ALTER TABLE movimientos ADD COLUMN pagado BOOLEAN DEFAULT FALSE"); conn.commit()
    except: conn.rollback() 
    try: c.execute("ALTER TABLE movimientos ADD COLUMN contrato TEXT DEFAULT ''"); conn.commit()
    except: conn.rollback()
    
    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deudas (id SERIAL PRIMARY KEY, nombre_deuda TEXT, monto_total REAL, moneda TEXT, fecha_inicio TEXT, estado TEXT)''')
    
    c.execute("SELECT count(*) FROM grupos")
    if c.fetchone()[0] == 0: c.executemany("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",), ("DEUDAS",)])
    
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0: c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", make_hashes("admin123")))
    conn.commit(); conn.close()

init_db()

# --- BACKUP SQL ---
def generar_backup_sql():
    try:
        conn = get_db_connection(); c = conn.cursor()
        tablas = ['grupos', 'users', 'deudas', 'movimientos']
        script = "-- BACKUP CONTABILIDAD PERSONAL V3 --\nTRUNCATE TABLE movimientos, deudas, grupos, users RESTART IDENTITY CASCADE;\n\n"
        for tabla in tablas:
            c.execute(f"SELECT * FROM {tabla}")
            rows = c.fetchall()
            if not rows: continue
            colnames = [desc[0] for desc in c.description]
            for row in rows:
                vals = []
                for v in row:
                    if v is None: vals.append("NULL")
                    elif isinstance(v, str): vals.append(f"'{v.replace("'", "''")}'") 
                    elif isinstance(v, bool): vals.append("TRUE" if v else "FALSE")
                    elif isinstance(v, (datetime.date, datetime.datetime)): vals.append(f"'{v}'")
                    else: vals.append(str(v))
                cols_str = ", ".join(colnames); vals_str = ", ".join(vals)
                script += f"INSERT INTO {tabla} ({cols_str}) VALUES ({vals_str}) ON CONFLICT DO NOTHING;\n"
        script += "\nSELECT setval('movimientos_id_seq', (SELECT MAX(id) FROM movimientos));\nSELECT setval('deudas_id_seq', (SELECT MAX(id) FROM deudas));\n"
        conn.close(); return script
    except Exception as e: return f"-- ERROR: {e}"

# --- LÓGICA ---
def calcular_monto_salario_mes(mes_str):
    if mes_str in SMVM_BASE_2026:
        base = SMVM_BASE_2026[mes_str]; monto = base * 2.5
        if "Junio" in mes_str: monto += (monto / 2)
        return monto
    if "2026" in mes_str:
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        try:
            nom = mes_str.split(" ")[0]
            if nom in ["Septiembre", "Octubre", "Noviembre", "Diciembre"]:
                ini = SMVM_BASE_2026["Enero 2026"]; fin = SMVM_BASE_2026["Agosto 2026"]
                prom = (fin - ini) / 7; idx_a = meses.index("Agosto"); idx_act = meses.index(nom)
                base = fin + (prom * (idx_act - idx_a)); monto = base * 2.5
                if nom == "Diciembre": monto += (monto / 2)
                return monto
        except: return None
    return None

def ejecutar_actualizacion_automatica_salarios():
    try:
        conn = get_db_connection(); c = conn.cursor()
        c.execute("SELECT id, mes FROM movimientos WHERE tipo_gasto = 'SALARIO CHICOS'")
        for reg in c.fetchall():
            val = calcular_monto_salario_mes(reg[1])
            if val: c.execute("UPDATE movimientos SET monto = %s WHERE id = %s", (val, reg[0]))
        conn.commit(); conn.close()
    except: pass

def ejecutar_actualizacion_automatica_terreno():
    try:
        conn = get_db_connection(); c = conn.cursor()
        for i, mes in enumerate(LISTA_MESES_LARGA):
            val = 13800.0 * ((1 + 0.04) ** i)
            c.execute("""UPDATE movimientos SET monto = %s WHERE mes = %s AND tipo_gasto = 'TERRENO'""", (val, mes))
        conn.commit(); conn.close()
    except: pass

def propagar_edicion_cuotas(mes_origen, concepto, contrato, grupo, monto, moneda, forma_pago, fecha_base, nueva_cuota_str):
    try:
        if "/" not in nueva_cuota_str: return
        actual, total = map(int, nueva_cuota_str.split('/'))
        if mes_origen not in LISTA_MESES_LARGA: return
        idx = LISTA_MESES_LARGA.index(mes_origen); conn = get_db_connection(); c = conn.cursor(); cuota_num = actual + 1
        while cuota_num <= total:
            idx += 1
            if idx >= len(LISTA_MESES_LARGA): break
            mf = LISTA_MESES_LARGA[idx]; cf = f"{cuota_num}/{total}"
            try: fstr = (pd.to_datetime(fecha_base) + datetime.timedelta(days=(cuota_num - actual) * 30)).strftime('%Y-%m-%d')
            except: fstr = str(datetime.date.today())
            c.execute("""UPDATE movimientos SET cuota=%s, monto=%s, moneda=%s, forma_pago=%s, fecha_pago=%s, contrato=%s WHERE mes=%s AND tipo_gasto=%s AND grupo=%s""", (cf, monto, moneda, forma_pago, fstr, contrato, mf, concepto, grupo))
            if c.rowcount == 0:
                c.execute("""INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s, %s, 'GASTO', %s, %s, %s, %s, %s, %s, %s, %s, FALSE)""", (str(datetime.date.today()), mf, grupo, concepto, contrato, cf, monto, moneda, forma_pago, fstr))
            cuota_num += 1
        conn.commit(); conn.close()
    except: pass

def actualizar_saldos_en_cascada(mes_modificado):
    try:
        conn = get_db_connection(); c = conn.cursor()
        if mes_modificado not in LISTA_MESES_LARGA: return
        idx = LISTA_MESES_LARGA.index(mes_modificado)
        for i in range(idx, min(len(LISTA_MESES_LARGA)-1, idx + 24)):
            ma = LISTA_MESES_LARGA[i]; ms = LISTA_MESES_LARGA[i+1]
            c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='GANANCIA' THEN monto ELSE 0 END),0) - COALESCE(SUM(CASE WHEN tipo='GASTO' THEN monto ELSE 0 END),0) FROM movimientos WHERE mes=%s AND moneda='ARS'""", (ma,))
            saldo = c.fetchone()[0] or 0.0
            c.execute("SELECT id FROM movimientos WHERE mes=%s AND tipo_gasto='Ahorro Mes Anterior'", (ms,))
            row = c.fetchone()
            if row: c.execute("UPDATE movimientos SET monto=%s WHERE id=%s", (saldo, row[0]))
            else: c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,'GANANCIA','AHORRO MANUEL','Ahorro Mes Anterior','1/1',%s,'ARS','Automático',%s)", (str(datetime.date.today()), ms, saldo, str(datetime.date.today())))
            conn.commit()
        conn.close()
    except: pass

@st.cache_data(ttl=60)
def get_dolar():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3).json()
        return (float(r['compra']) + float(r['venta'])) / 2, f"(Venta: ${int(r['venta'])})"
    except: return 1480.0, "(Ref)"

# --- LOGIN ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ''

def login_page():
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
                if c.fetchall(): st.session_state['logged_in'] = True; st.session_state['username'] = u; st.rerun()
                else: st.error("Error")
                conn.close()

if not st.session_state['logged_in']: login_page(); st.stop()

# ==========================================
# APP
# ==========================================
with st.sidebar:
    lottie = load_lottieurl(LOTTIE_FINANCE)
    if lottie: st_lottie(lottie, height=100)
    st.write(f"👤 **{st.session_state['username']}**")
    if st.button("Salir"): st.session_state['logged_in'] = False; st.rerun()

dolar_val, dolar_info = get_dolar()
st.title("CONTABILIDAD PERSONAL V3")
mes_global = st.selectbox("📅 MES DE TRABAJO:", LISTA_MESES_LARGA)

ejecutar_actualizacion_automatica_salarios()
ejecutar_actualizacion_automatica_terreno()

conn = get_db_connection()
grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
df_all = pd.read_sql("SELECT * FROM movimientos", conn)
conn.close()

st.sidebar.header("📥 CARGAR NUEVO")
with st.sidebar.form("alta"):
    t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
    g_sel = st.selectbox("GRUPO", grupos_db)
    
    # CAMBIO DE NOMBRE EN ETIQUETA
    c_con, c_cont = st.columns(2)
    concepto = c_con.text_input("CONCEPTO")
    contrato = c_cont.text_input("CUENTA O CONTRATO") # CAMBIO AQUI
    
    c1, c2 = st.columns(2)
    c_act = c1.number_input("Cuota", 1, 300, 1)
    c_tot = c2.number_input("Total (1 = Sin Cuotas)", 1, 300, 1)
    m_input = st.text_input("MONTO", "0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("PAGO", OPCIONES_PAGO)
    f_fecha = st.date_input("FECHA PAGO", datetime.date(2026, 1, 1))
    ya_pagado = st.checkbox("¿Ya está pagado/confirmado?")
    
    if st.form_submit_button("GRABAR"):
        m_final = procesar_monto_input(m_input)
        conn = get_db_connection(); c = conn.cursor()
        idx = LISTA_MESES_LARGA.index(mes_global)
        
        if c_tot == 1:
            vc = calcular_monto_salario_mes(mes_global)
            mg = vc if (concepto.strip().upper() == "SALARIO CHICOS" and vc) else m_final
            c.execute("""INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                (str(datetime.date.today()), mes_global, t_sel, g_sel, concepto, contrato, "", mg, mon_sel, f_pago, f_fecha.strftime('%Y-%m-%d'), ya_pagado))
        else:
            for i in range(int(c_act), int(c_tot)+1):
                off = i - int(c_act)
                if idx + off < len(LISTA_MESES_LARGA):
                    mt = LISTA_MESES_LARGA[idx + off]
                    vc = calcular_monto_salario_mes(mt)
                    mg = vc if (concepto.strip().upper() == "SALARIO CHICOS" and vc) else m_final
                    cstr = f"{i}/{int(c_tot)}"
                    fv = f_fecha + datetime.timedelta(days=30*off)
                    ep = ya_pagado if off == 0 else False
                    c.execute("""INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", 
                        (str(datetime.date.today()), mt, t_sel, g_sel, concepto, contrato, cstr, mg, mon_sel, f_pago, fv.strftime('%Y-%m-%d'), ep))
        conn.commit(); conn.close(); actualizar_saldos_en_cascada(mes_global)
        enviar_notificacion("Nuevo Movimiento", f"{concepto} - {contrato} - {m_final}")
        st.balloons(); st.success("Guardado"); st.rerun()

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 DASHBOARD", "🔮 PREDICCIONES", "⚙️ CONFIGURACIÓN", "📉 DEUDAS"])

with tab1:
    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    df_mes = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_mes.empty:
        # KPI
        res_ars = df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GANANCIA")]['monto'].sum() - df_mes[(df_mes['moneda']=="ARS")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        res_usd = df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GANANCIA")]['monto'].sum() - df_mes[(df_mes['moneda']=="USD")&(df_mes['tipo']=="GASTO")]['monto'].sum()
        pat = res_ars + (res_usd * dolar_val)
        c1, c2, c3 = st.columns(3)
        c1.metric("RESULTADO (ARS)", formato_moneda_visual(res_ars, "ARS"))
        c2.metric("RESULTADO (USD)", formato_moneda_visual(res_usd, "USD"))
        c3.metric("PATRIMONIO TOTAL ($)", formato_moneda_visual(pat, "ARS"))
        st.divider()

        # CALENDARIO
        try:
            mn, an = mes_global.split(" "); av = int(an)
            md = {"Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6,"Julio":7,"Agosto":8,"Septiembre":9,"Octubre":10,"Noviembre":11,"Diciembre":12}
            mv = md.get(mn, 1); _, nd = calendar.monthrange(av, mv)
            fechas = [datetime.date(av, mv, d) for d in range(1, nd+1)]
            dfc = df_mes.copy(); dfc['fd'] = pd.to_datetime(dfc['fecha_pago']).dt.date
            cdata = []
            for f in fechas:
                mdia = dfc[dfc['fd'] == f]['monto'].sum()
                cdata.append({"Dia": f.day, "Sem": int(f.strftime("%U")), "DS": f.weekday(), "M": mdia, "C": mdia if mdia>0 else 0})
            dfcal = pd.DataFrame(cdata); dfcal['SR'] = dfcal['Sem'] - dfcal['Sem'].min()
            
            fig = go.Figure(data=go.Scatter(
                x=dfcal['DS'], y=dfcal['SR'], text=dfcal['Dia'], mode='markers+text',
                marker=dict(size=45, symbol='square', color=dfcal['C'], colorscale='Greens', showscale=False, line=dict(width=1, color='gray')),
                textfont=dict(color='black', size=12), hovertext=[f"${r.M:,.0f}" for i, r in dfcal.iterrows()]))
            
            fig.update_layout(
                title=dict(text=f"📅 {mes_global}", x=0.5),
                xaxis=dict(tickvals=[0,1,2,3,4,5,6], ticktext=["L","M","M","J","V","S","D"], side='top', showgrid=False, zeroline=False, range=[-0.5, 6.5]),
                yaxis=dict(autorange="reversed", showticklabels=False, showgrid=False, zeroline=False, scaleanchor='x', scaleratio=1),
                height=350, margin=dict(l=20, r=20, t=60, b=20), clickmode='event+select', 
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            
            sel = st.plotly_chart(fig, on_select="rerun", selection_mode="points", use_container_width=True)
            if sel and sel["selection"]["points"]:
                d = int(sel["selection"]["points"][0]["text"])
                st.info(f"🔎 Día {d}"); df_mes = df_mes[pd.to_datetime(df_mes['fecha_pago']).dt.day == d]
        except: pass

        # GRAFICOS
        df_mes['m_ars_v'] = df_mes.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        
        c_g1, c_g2 = st.columns(2)
        with c_g1: 
            st.caption("Distribución de Gastos")
            if not df_mes[df_mes['tipo']=="GASTO"].empty:
                st.plotly_chart(px.pie(df_mes[df_mes['tipo']=="GASTO"], values='m_ars_v', names='grupo', hole=0.4), use_container_width=True)
        with c_g2:
            st.caption("Gastos por Forma de Pago")
            df_fp = df_mes[df_mes['tipo']=="GASTO"].groupby('forma_pago')['m_ars_v'].sum().reset_index()
            if not df_fp.empty:
                st.plotly_chart(px.bar(df_fp, x='forma_pago', y='m_ars_v', color='forma_pago', labels={'forma_pago': 'Forma de Pago'}), use_container_width=True)

        COLOR_MAP = {"GANANCIA": "#28a745", "GASTO": "#dc3545"}
        c_ars, c_usd = st.columns(2)
        with c_ars:
            st.caption("Flujo Pesos")
            if not df_mes[df_mes['moneda']=="ARS"].empty:
                st.plotly_chart(px.bar(df_mes[df_mes['moneda']=="ARS"].groupby('tipo')['monto'].sum().reset_index(), 
                                     x='tipo', y='monto', color='tipo', color_discrete_map=COLOR_MAP), use_container_width=True)
        with c_usd:
            st.caption("Flujo Dólares")
            if not df_mes[df_mes['moneda']=="USD"].empty:
                st.plotly_chart(px.bar(df_mes[df_mes['moneda']=="USD"].groupby('tipo')['monto'].sum().reset_index(), 
                                     x='tipo', y='monto', color='tipo', color_discrete_map=COLOR_MAP), use_container_width=True)
        st.markdown("---") 
        
        # TABLA
        df_mes['monto_visual'] = df_mes.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        if 'pagado' not in df_mes.columns: df_mes['pagado'] = False
        df_mes['pagado'] = df_mes['pagado'].fillna(False).astype(bool)
        df_mes['estado'] = df_mes['pagado'].apply(lambda x: "✅" if x else "⏳")
        if 'contrato' not in df_mes.columns: df_mes['contrato'] = "" 

        cols = ["estado", "tipo_gasto", "contrato", "monto_visual", "cuota", "forma_pago", "fecha_pago", "pagado"]
        col_cfg = {
            "estado": st.column_config.TextColumn("✅", width="small"),
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"),
            "contrato": st.column_config.TextColumn("CUENTA O CONTRATO"), # CAMBIO AQUI
            "monto_visual": st.column_config.TextColumn("MONTO", width="medium"),
            "cuota": st.column_config.TextColumn("CUOTA", width="small"),
            "forma_pago": st.column_config.TextColumn("FORMA PAGO", width="medium"),
            "fecha_pago": st.column_config.DateColumn("FECHA PAGO", format="DD/MM/YYYY", width="medium"),
            "pagado": st.column_config.CheckboxColumn("PAGADO")
        }
        
        def style_fn(row): return ['background-color: #1c3323' if row['pagado'] else ''] * len(row)
        selected_records = []

        for gran_tipo in ["GANANCIA", "GASTO"]:
            df_t = df_mes[df_mes['tipo'] == gran_tipo]
            if not df_t.empty:
                st.markdown(f"## {'🟢' if gran_tipo=='GANANCIA' else '🔴'} {gran_tipo}S")
                for grp in sorted(df_t['grupo'].unique()):
                    with st.container():
                        st.subheader(f"📂 {grp}")
                        df_g = df_t[df_t['grupo'] == grp]
                        sty = df_g[cols].style.apply(style_fn, axis=1)
                        
                        sel = st.dataframe(sty, column_config=col_cfg, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"tbl_{gran_tipo}_{grp}_{mes_global}")
                        
                        subt = df_g['m_ars_v'].sum()
                        st.markdown(f"<div style='text-align: left; margin-bottom: 20px;'><strong>💰 Subtotal {grp}: {formato_moneda_visual(subt, 'ARS')}</strong></div>", unsafe_allow_html=True)
                        if sel.selection.rows:
                            for idx in sel.selection.rows: selected_records.append(df_g.iloc[idx])
                st.divider()

        if len(selected_records) == 1:
            row = selected_records[0]; id_mov = int(row['id'])
            st.markdown(f"### ✏️ {row['tipo_gasto']}")
            with st.form("edit"):
                c1, c2, c3, c4 = st.columns(4)
                nT = c1.selectbox("Tipo", ["GASTO", "GANANCIA"], index=["GASTO", "GANANCIA"].index(row['tipo']))
                nG = c2.selectbox("Grupo", grupos_db, index=grupos_db.index(row['grupo']) if row['grupo'] in grupos_db else 0)
                nC = c3.text_input("Concepto", value=row['tipo_gasto'])
                nCont = c4.text_input("Cuenta o Contrato", value=row['contrato'] if row['contrato'] else "") # CAMBIO AQUI
                
                c5, c6, c7 = st.columns(3)
                nM = c5.text_input("Monto", value=str(row['monto']))
                nMon = c6.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(row['moneda']))
                nCuo = c7.text_input("Cuota", value=str(row['cuota']))
                
                c8, c9, c10 = st.columns(3)
                nP = c8.selectbox("Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(row['forma_pago']) if row['forma_pago'] in OPCIONES_PAGO else 0)
                try: fd = pd.to_datetime(row['fecha_pago']).date()
                except: fd = datetime.date.today()
                nF = c9.date_input("Fecha", value=fd)
                nPag = c10.checkbox("✅ MARCAR COMO PAGADO", value=bool(row['pagado']))
                
                b1, b2 = st.columns([1,1]); conn = get_db_connection(); c = conn.cursor()
                if b1.form_submit_button("💾 GUARDAR"):
                    mf = procesar_monto_input(nM); vc = calcular_monto_salario_mes(row['mes'])
                    if nC.strip().upper() == "SALARIO CHICOS" and vc: mf = vc
                    c.execute("UPDATE movimientos SET tipo=%s, grupo=%s, tipo_gasto=%s, contrato=%s, monto=%s, moneda=%s, cuota=%s, forma_pago=%s, fecha_pago=%s, pagado=%s WHERE id=%s", (nT, nG, nC, nCont, mf, nMon, nCuo, nP, str(nF), nPag, id_mov))
                    conn.commit()
                    if nCuo != row['cuota']: propagar_edicion_cuotas(mes_global, nC, nCont, nG, mf, nMon, nP, str(nF), nCuo)
                    conn.close(); actualizar_saldos_en_cascada(row['mes']); enviar_notificacion("Edición", f"{nC} editado"); st.success("Editado"); st.rerun()
                if b2.form_submit_button("❌ ELIMINAR", type="primary"):
                    c.execute("DELETE FROM movimientos WHERE id=%s", (id_mov,)); conn.commit(); conn.close()
                    actualizar_saldos_en_cascada(row['mes']); st.warning("Eliminado"); st.rerun()

        elif len(selected_records) > 1:
            st.warning(f"Seleccionados: {len(selected_records)}")
            c1, c2, c3, c4 = st.columns(4)
            nd = c1.date_input("Nueva Fecha", datetime.date.today())
            np = c2.selectbox("Nueva Forma Pago", OPCIONES_PAGO)
            mp = c3.checkbox("✅ MARCAR TODOS PAGADOS")
            if c4.button("💾 ACTUALIZAR TODO"):
                conn = get_db_connection(); c = conn.cursor()
                ids = tuple([int(r['id']) for r in selected_records])
                if mp: c.execute("UPDATE movimientos SET fecha_pago=%s, forma_pago=%s, pagado=TRUE WHERE id IN %s", (str(nd), np, ids))
                else: c.execute("UPDATE movimientos SET fecha_pago=%s, forma_pago=%s WHERE id IN %s", (str(nd), np, ids))
                conn.commit(); conn.close(); st.success("Actualizado"); st.rerun()
            if st.button("❌ ELIMINAR TODOS", type="primary"):
                conn = get_db_connection(); c = conn.cursor()
                ids = tuple([int(r['id']) for r in selected_records])
                c.execute("DELETE FROM movimientos WHERE id IN %s", (ids,)); conn.commit(); conn.close()
                actualizar_saldos_en_cascada(mes_global); st.success("Eliminados"); st.rerun()
    else: st.info("Sin datos.")

with tab2: # PREDICCIONES
    st.header("🔮 Predicciones")
    df_ai = df_all[df_all['tipo'] == 'GASTO'].copy()
    if len(df_ai) > 0:
        df_ai['m_norm'] = df_ai.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        mapa = {m: i+1 for i, m in enumerate(LISTA_MESES_LARGA)}
        df_ai['mes_num'] = df_ai['mes'].map(mapa)
        df_m = df_ai.groupby('mes_num')['m_norm'].sum().reset_index().sort_values('mes_num')
        if len(df_m) >= 2:
            model = LinearRegression(); model.fit(df_m['mes_num'].values.reshape(-1, 1), df_m['m_norm'].values)
            prox = df_m['mes_num'].max() + 1; pred = model.predict([[prox]])[0]
            st.metric("Proyección Próximo Mes", formato_moneda_visual(pred, "ARS"))
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_m['mes_num'], y=df_m['m_norm'], mode='lines+markers', name='Real'))
            fig.add_trace(go.Scatter(x=df_m['mes_num'], y=model.predict(df_m['mes_num'].values.reshape(-1, 1)), mode='lines', name='Tendencia'))
            st.plotly_chart(fig, use_container_width=True)
    else: st.info("Faltan datos.")

with tab3: # CONFIG
    st.header("⚙️ Configuración")
    st.markdown("### 💾 EXPORTAR DATOS")
    sql = generar_backup_sql()
    st.download_button("📦 BACKUP SQL (MIGRACIÓN)", sql, "backup.sql", "text/plain", type="primary")
    conn = get_db_connection()
    cm = pd.read_sql("SELECT * FROM movimientos", conn).to_csv(index=False).encode('utf-8')
    cd = pd.read_sql("SELECT * FROM deudas", conn).to_csv(index=False).encode('utf-8')
    conn.close()
    c1, c2 = st.columns(2)
    c1.download_button("📥 Movimientos (CSV)", cm, "movimientos.csv", "text/csv")
    c2.download_button("📥 Deudas (CSV)", cd, "deudas.csv", "text/csv")
    st.divider()
    with st.expander("🏷️ GRUPOS"):
        c1, c2 = st.columns(2); conn = get_db_connection(); c = conn.cursor()
        with c1: 
            if st.button("Crear"): c.execute("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", (st.text_input("Nuevo").upper(),)); conn.commit(); st.rerun()
        with c2:
            dg = st.selectbox("Borrar", grupos_db)
            if st.button("Eliminar"): c.execute("DELETE FROM grupos WHERE nombre=%s", (dg,)); conn.commit(); st.rerun()
        conn.close()
    st.divider()
    c1, c2, c3 = st.columns(3); ms = c1.selectbox("Desde", LISTA_MESES_LARGA); md = c2.selectbox("Hasta", ["TODO"]+LISTA_MESES_LARGA)
    if c3.button("🚀 CLONAR"):
        conn = get_db_connection(); c = conn.cursor()
        src = pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{ms}'", conn)
        tgs = [m for m in LISTA_MESES_LARGA if m.split(' ')[1] == ms.split(' ')[1]] if md == "TODO" else [md]
        for t in tgs:
            if t == ms: continue
            c.execute("DELETE FROM movimientos WHERE mes=%s", (t,)); 
            for _, r in src.iterrows():
                contr = r['contrato'] if 'contrato' in r else ""
                c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()), t, r['tipo'], r['grupo'], r['tipo_gasto'], contr, r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
        conn.commit(); st.success("Clonado"); st.rerun()

with tab4: # DEUDAS
    st.header("📉 Deudas")
    c1, c2 = st.columns([1, 2]); conn = get_db_connection(); c = conn.cursor()
    with c1:
        with st.form("fd"):
            n = st.text_input("Nombre"); m = st.text_input("Total"); mon = st.selectbox("Moneda", ["ARS", "USD"])
            if st.form_submit_button("Crear"):
                c.execute("INSERT INTO deudas (nombre_deuda, monto_total, moneda, fecha_inicio, estado) VALUES (%s,%s,%s,%s,'ACTIVA')", (n, procesar_monto_input(m), mon, str(datetime.date.today())))
                conn.commit(); st.rerun()
    with c2:
        ddf = pd.read_sql("SELECT * FROM deudas WHERE estado='ACTIVA'", conn)
        if not ddf.empty:
            for _, d in ddf.iterrows():
                with st.expander(f"{d['nombre_deuda']} ({formato_moneda_visual(d['monto_total'], d['moneda'])})", expanded=True):
                    c.execute("SELECT id, fecha_pago, monto FROM movimientos WHERE grupo='DEUDAS' AND tipo_gasto LIKE %s AND moneda=%s", (f"%{d['nombre_deuda']}%", d['moneda']))
                    pags = c.fetchall(); tot_p = sum([p[2] for p in pags]); rest = d['monto_total'] - tot_p
                    st.progress(min(tot_p/d['monto_total'], 1.0) if d['monto_total']>0 else 0)
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Total", formato_moneda_visual(d['monto_total'], d['moneda']))
                    k2.metric("Pagado", formato_moneda_visual(tot_p, d['moneda']))
                    k3.metric("Falta", formato_moneda_visual(rest, d['moneda']))
                    if pags:
                        st.markdown("###### 📜 Historial")
                        for p in pags:
                            h1, h2, h3 = st.columns([2,2,1])
                            h1.write(p[1]); h2.write(formato_moneda_visual(p[2], d['moneda']))
                            if h3.button("🗑️", key=f"dp_{p[0]}"): c.execute("DELETE FROM movimientos WHERE id=%s", (p[0],)); conn.commit(); st.rerun()
                        st.markdown("---")
                    if rest <= 0:
                        st.success("¡PAGADA!")
                        if st.button("Archivar", key=f"ar_{d['id']}"): c.execute("UPDATE deudas SET estado='PAGADA' WHERE id=%s", (d['id'],)); conn.commit(); st.rerun()
                    else:
                        r1, r2 = st.columns(2); mp = r1.text_input("Monto", key=f"m_{d['id']}"); fp = r2.selectbox("Pago", OPCIONES_PAGO, key=f"f_{d['id']}")
                        if st.button("💸 Pagar", key=f"b_{d['id']}"):
                            c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,'GASTO','DEUDAS',%s,'',%s,%s,%s,%s,TRUE)", (str(datetime.date.today()), mes_global, f"Pago: {d['nombre_deuda']}", procesar_monto_input(mp), d['moneda'], fp, str(datetime.date.today())))
                            conn.commit(); st.rerun()
                    st.markdown("---")
                    if st.button("❌ ELIMINAR", key=f"x_{d['id']}", type="primary"): c.execute("DELETE FROM deudas WHERE id=%s", (d['id'],)); conn.commit(); st.rerun()
        else: st.info("Sin deudas.")
    conn.close()