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

# --- CARGAR VARIABLES ---
load_dotenv()

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="SMART FINANCE PRO", layout="wide")

# --- GENERADOR DE MESES ---
def generar_lista_meses(start_year=2026, end_year=2035):
    meses_base = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
                  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    lista = []
    for anio in range(start_year, end_year + 1):
        for mes in meses_base:
            lista.append(f"{mes} {anio}")
    return lista

LISTA_MESES_LARGA = generar_lista_meses()
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]

# --- DATOS BASE PARA SALARIO CHICOS (SMVM) ---
SMVM_BASE_2026 = {
    "Enero 2026": 341000.0,
    "Febrero 2026": 346800.0,
    "Marzo 2026": 352400.0,
    "Abril 2026": 357800.0,
    "Mayo 2026": 363000.0,
    "Junio 2026": 367800.0,
    "Julio 2026": 372400.0,
    "Agosto 2026": 376600.0
}

# --- FUNCIONES AUXILIARES ---
def load_lottieurl(url):
    try:
        r = requests.get(url)
        if r.status_code != 200: return None
        return r.json()
    except: return None

LOTTIE_FINANCE = "https://lottie.host/02a55953-2736-4763-b183-116515b81045/L1O1fW89yB.json" 

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
    # Tabla Movimientos
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos 
                 (id SERIAL PRIMARY KEY, fecha TEXT, mes TEXT, 
                  tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT,
                  forma_pago TEXT, fecha_pago TEXT)''')
    
    # --- MIGRACIÓN AUTOMÁTICA: AGREGAR COLUMNA PAGADO ---
    try:
        c.execute("ALTER TABLE movimientos ADD COLUMN pagado BOOLEAN DEFAULT FALSE")
        conn.commit()
    except:
        conn.rollback() 

    # Tabla Grupos
    c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
    # Tabla Usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    # Tabla Deudas
    c.execute('''CREATE TABLE IF NOT EXISTS deudas 
                 (id SERIAL PRIMARY KEY, nombre_deuda TEXT, monto_total REAL, moneda TEXT, fecha_inicio TEXT, estado TEXT)''')
    
    c.execute("SELECT count(*) FROM grupos")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",), ("DEUDAS",)])
    
    c.execute("SELECT count(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", make_hashes("admin123")))
    
    conn.commit()
    conn.close()

init_db()

# --- LÓGICA AUTOMÁTICA SALARIO CHICOS ---

def calcular_monto_salario_mes(mes_str):
    if mes_str in SMVM_BASE_2026:
        base = SMVM_BASE_2026[mes_str]
        monto = base * 2.5
        if "Junio" in mes_str:
            monto = monto + (monto / 2)
        return monto
    
    if "2026" in mes_str:
        meses_orden = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        try:
            nombre_mes = mes_str.split(" ")[0]
            if nombre_mes in ["Septiembre", "Octubre", "Noviembre", "Diciembre"]:
                inicio = SMVM_BASE_2026["Enero 2026"]
                fin = SMVM_BASE_2026["Agosto 2026"]
                aumento_promedio = (fin - inicio) / 7
                idx_agosto = meses_orden.index("Agosto")
                idx_actual = meses_orden.index(nombre_mes)
                meses_extra = idx_actual - idx_agosto
                
                base_proyectada = fin + (aumento_promedio * meses_extra)
                monto_proyectado = base_proyectada * 2.5
                
                if nombre_mes == "Diciembre":
                    monto_proyectado = monto_proyectado + (monto_proyectado / 2)
                    
                return monto_proyectado
        except: return None
    return None

def ejecutar_actualizacion_automatica_salarios():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, mes FROM movimientos WHERE tipo_gasto = 'SALARIO CHICOS'")
        registros = c.fetchall()
        for reg in registros:
            id_mov = reg[0]
            mes_mov = reg[1]
            valor_correcto = calcular_monto_salario_mes(mes_mov)
            if valor_correcto is not None:
                c.execute("UPDATE movimientos SET monto = %s WHERE id = %s", (valor_correcto, id_mov))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Error auto-salarios: {e}")

# --- LÓGICA AUTOMÁTICA TERRENO ---

def ejecutar_actualizacion_automatica_terreno():
    try:
        base = 13800.0
        tasa_mensual = 0.04
        conn = get_db_connection()
        c = conn.cursor()
        for i, mes in enumerate(LISTA_MESES_LARGA):
            monto_terreno = base * ((1 + tasa_mensual) ** i)
            c.execute("""UPDATE movimientos SET monto = %s WHERE mes = %s AND tipo_gasto = 'TERRENO'""", (monto_terreno, mes))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"Error auto-terreno: {e}")

# --- CASCADA DE CUOTAS ---

def propagar_edicion_cuotas(mes_origen, concepto, grupo, monto, moneda, forma_pago, fecha_base, nueva_cuota_str):
    try:
        if "/" not in nueva_cuota_str: return
        actual, total = map(int, nueva_cuota_str.split('/'))
        if mes_origen not in LISTA_MESES_LARGA: return
        idx_mes = LISTA_MESES_LARGA.index(mes_origen)
        conn = get_db_connection()
        c = conn.cursor()
        cuota_num = actual + 1
        
        while cuota_num <= total:
            idx_mes += 1
            if idx_mes >= len(LISTA_MESES_LARGA): break
            mes_futuro = LISTA_MESES_LARGA[idx_mes]
            cuota_futura = f"{cuota_num}/{total}"
            dias_offset = (cuota_num - actual) * 30
            try:
                fecha_base_dt = pd.to_datetime(fecha_base)
                fecha_futura_dt = fecha_base_dt + datetime.timedelta(days=dias_offset)
                try: fecha_futura_str = fecha_futura_dt.strftime('%Y-%m-%d')
                except: fecha_futura_str = str(datetime.date.today())
            except: fecha_futura_str = str(datetime.date.today())

            c.execute("""UPDATE movimientos SET cuota = %s, monto = %s, moneda = %s, forma_pago = %s, fecha_pago = %s
                WHERE mes = %s AND tipo_gasto = %s AND grupo = %s""", 
                (cuota_futura, monto, moneda, forma_pago, fecha_futura_str, mes_futuro, concepto, grupo))
            
            if c.rowcount == 0:
                c.execute("""INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago)
                    VALUES (%s, %s, 'GASTO', %s, %s, %s, %s, %s, %s, %s)""", 
                    (str(datetime.date.today()), mes_futuro, grupo, concepto, cuota_futura, monto, moneda, forma_pago, fecha_futura_str))
            
            cuota_num += 1
        conn.commit(); conn.close()
    except Exception as e: print(f"Error cuotas: {e}")

def actualizar_saldos_en_cascada(mes_modificado):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        if mes_modificado not in LISTA_MESES_LARGA: return
        idx_inicio = LISTA_MESES_LARGA.index(mes_modificado)
        rango = min(len(LISTA_MESES_LARGA)-1, idx_inicio + 24)
        for i in range(idx_inicio, rango):
            mes_act = LISTA_MESES_LARGA[i]
            mes_sig = LISTA_MESES_LARGA[i+1]
            c.execute("""SELECT COALESCE(SUM(CASE WHEN tipo='GANANCIA' THEN monto ELSE 0 END),0) - COALESCE(SUM(CASE WHEN tipo='GASTO' THEN monto ELSE 0 END),0) FROM movimientos WHERE mes=%s AND moneda='ARS'""", (mes_act,))
            saldo = c.fetchone()[0] or 0.0
            c.execute("SELECT id FROM movimientos WHERE mes=%s AND tipo_gasto='Ahorro Mes Anterior'", (mes_sig,))
            row = c.fetchone()
            hoy = str(datetime.date.today())
            if row: c.execute("UPDATE movimientos SET monto=%s WHERE id=%s", (saldo, row[0]))
            else: c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,'GANANCIA','AHORRO MANUEL','Ahorro Mes Anterior','1/1',%s,'ARS','Automático',%s)", (hoy, mes_sig, saldo, hoy))
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
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ''

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESO FINANZAS</h1>", unsafe_allow_html=True)
    lottie_login = load_lottieurl(LOTTIE_FINANCE) 
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
                else: st.error("Error")
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

dolar_val, dolar_info = get_dolar()

st.title("SMART FINANCE PRO")
mes_global = st.selectbox("📅 MES DE TRABAJO:", LISTA_MESES_LARGA)

# --- EJECUCIÓN AUTOMÁTICA ---
ejecutar_actualizacion_automatica_salarios()
ejecutar_actualizacion_automatica_terreno()

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
    c_tot = c2.number_input("Total (1 = Sin Cuotas)", 1, 300, 1)
    m_input = st.text_input("MONTO", "0,00")
    mon_sel = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
    f_pago = st.selectbox("PAGO", OPCIONES_PAGO)
    f_fecha = st.date_input("FECHA PAGO", datetime.date(2026, 1, 1))
    
    ya_pagado = st.checkbox("¿YA ESTÁ PAGADO?")
    
    if st.form_submit_button("GRABAR"):
        m_final = procesar_monto_input(m_input)
        conn = get_db_connection()
        c = conn.cursor()
        idx_base = LISTA_MESES_LARGA.index(mes_global)
        
        cuota_actual = int(c_act)
        total_cuotas = int(c_tot)
        
        if total_cuotas == 1:
            mes_t = mes_global
            monto_guardar = m_final
            val_calc = calcular_monto_salario_mes(mes_t)
            if concepto.strip().upper() == "SALARIO CHICOS" and val_calc is not None:
                monto_guardar = val_calc
                
            c.execute("""INSERT INTO movimientos 
                (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago, pagado) 
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (str(datetime.date.today()), mes_t, t_sel, g_sel, concepto, "", monto_guardar, mon_sel, f_pago, f_fecha.strftime('%Y-%m-%d'), ya_pagado))
        
        else:
            for i in range(cuota_actual, total_cuotas + 1):
                offset = i - cuota_actual
                if idx_base + offset < len(LISTA_MESES_LARGA):
                    mes_t = LISTA_MESES_LARGA[idx_base + offset]
                    
                    monto_guardar = m_final
                    val_calc = calcular_monto_salario_mes(mes_t)
                    if concepto.strip().upper() == "SALARIO CHICOS" and val_calc is not None:
                        monto_guardar = val_calc

                    cuota_str = f"{i}/{total_cuotas}"
                    fecha_v = f_fecha + datetime.timedelta(days=30*offset)
                    
                    es_pagado_cuota = ya_pagado if offset == 0 else False
                    
                    c.execute("""INSERT INTO movimientos 
                        (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago, pagado) 
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (str(datetime.date.today()), mes_t, t_sel, g_sel, concepto, cuota_str, monto_guardar, mon_sel, f_pago, fecha_v.strftime('%Y-%m-%d'), es_pagado_cuota))
        
        conn.commit(); conn.close()
        actualizar_saldos_en_cascada(mes_global)
        st.balloons(); st.success("Guardado"); st.rerun()

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 DASHBOARD", "🔮 PREDICCIONES", "⚙️ CONFIGURACIÓN", "📉 DEUDAS / PAGOS PARCIALES"])

with tab1:
    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")
    
    df_mes = df_all[df_all['mes'] == mes_global].copy()
    
    if not df_mes.empty:
        # KPI
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
        
        c_graf_1, c_graf_2 = st.columns(2)
        with c_graf_1:
            st.caption("Distribución de Gastos")
            if not df_mes_graf[df_mes_graf['tipo']=="GASTO"].empty:
                st.plotly_chart(px.pie(df_mes_graf[df_mes_graf['tipo']=="GASTO"], values='m_ars_v', names='grupo', hole=0.4), use_container_width=True)
        with c_graf_2:
            st.caption("Gastos por Forma de Pago")
            df_fp = df_mes_graf[df_mes_graf['tipo']=="GASTO"].groupby('forma_pago')['m_ars_v'].sum().reset_index()
            if not df_fp.empty:
                st.plotly_chart(px.bar(df_fp, x='forma_pago', y='m_ars_v', color='forma_pago'), use_container_width=True)

        col_ars, col_usd = st.columns(2)
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
        
        # TABLAS JERARQUICAS CON ESTILO
        df_view = df_mes.copy()
        df_view['monto_visual'] = df_view.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        
        if 'pagado' not in df_view.columns: df_view['pagado'] = False
        df_view['pagado'] = df_view['pagado'].fillna(False).astype(bool)
        df_view['estado'] = df_view['pagado'].apply(lambda x: "✅" if x else "⏳")

        cols_show = ["estado", "tipo_gasto", "monto_visual", "cuota", "forma_pago", "fecha_pago", "pagado"]
        
        # DEFINICIÓN CORRECTA DE COLUMN CONFIG
        col_cfg = {
            "estado": st.column_config.TextColumn("✅", width="small"),
            "tipo_gasto": st.column_config.TextColumn("CONCEPTO"),
            "monto_visual": st.column_config.TextColumn("MONTO", width="medium"),
            "cuota": st.column_config.TextColumn("CUOTA", width="small"),
            "forma_pago": st.column_config.TextColumn("FORMA PAGO", width="medium"),
            "fecha_pago": st.column_config.DateColumn("FECHA PAGO", format="DD/MM/YYYY", width="medium"),
        }

        # Estilo para pintar de verde
        def estilo_pagados(row):
            color = 'background-color: #1c3323' if row['pagado'] else ''
            return [color] * len(row)

        selected_records = []

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
                        
                        # APLICAR ESTILO
                        styled_df = df_grp[cols_show].style.apply(estilo_pagados, axis=1)
                        
                        selection = st.dataframe(
                            styled_df,
                            column_config=col_cfg, 
                            use_container_width=True, 
                            hide_index=True, 
                            on_select="rerun", 
                            column_order=["estado", "tipo_gasto", "monto_visual", "cuota", "forma_pago", "fecha_pago"], # ORDEN EXPLICITO EXCLUYE 'pagado'
                            selection_mode="multi-row",
                            key=f"tbl_{gran_tipo}_{grp}_{mes_global}"
                        )
                        
                        subtotal_ars = df_grp.apply(
                            lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], 
                            axis=1
                        ).sum()
                        
                        st.markdown(f"""
                        <div style="background-color: #262730; padding: 8px; border-radius: 5px; margin-bottom: 20px; text-align: left;">
                            <strong>💰 Subtotal {grp}: {formato_moneda_visual(subtotal_ars, 'ARS')}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if selection.selection.rows:
                            for idx in selection.selection.rows:
                                selected_records.append(df_grp.iloc[idx])
                st.divider()

        # ACCIONES
        if len(selected_records) == 1:
            row_to_edit = selected_records[0]
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
                c_e7, c_e8, c_e9 = st.columns(3)
                new_pago = c_e7.selectbox("Forma Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(row_to_edit['forma_pago']) if row_to_edit['forma_pago'] in OPCIONES_PAGO else 0)
                try: f_dt = pd.to_datetime(row_to_edit['fecha_pago']).date()
                except: f_dt = datetime.date(2026, 1, 1)
                new_f = c_e8.date_input("Fecha Pago", value=f_dt)
                
                val_pagado = bool(row_to_edit['pagado'])
                new_pagado = c_e9.checkbox("✅ MARCAR COMO PAGADO", value=val_pagado)
                
                b1, b2 = st.columns([1, 1])
                conn = get_db_connection(); c = conn.cursor()
                
                if b1.form_submit_button("💾 GUARDAR CAMBIOS"):
                    m_f = procesar_monto_input(new_m)
                    val_calc = calcular_monto_salario_mes(row_to_edit['mes'])
                    if new_c.strip().upper() == "SALARIO CHICOS" and val_calc is not None:
                        m_f = val_calc
                    
                    c.execute("""UPDATE movimientos 
                        SET tipo=%s, grupo=%s, tipo_gasto=%s, monto=%s, moneda=%s, cuota=%s, forma_pago=%s, fecha_pago=%s, pagado=%s 
                        WHERE id=%s""", 
                        (new_tipo, new_g, new_c, m_f, new_mon, new_cuota, new_pago, str(new_f), new_pagado, id_mov))
                    conn.commit()
                    if new_cuota != row_to_edit['cuota']:
                        propagar_edicion_cuotas(mes_global, new_c, new_g, m_f, new_mon, new_pago, new_f, new_cuota)
                    conn.close()
                    actualizar_saldos_en_cascada(row_to_edit['mes']) 
                    st.success("Editado"); st.rerun()
                
                if b2.form_submit_button("❌ ELIMINAR", type="primary"):
                    c.execute("DELETE FROM movimientos WHERE id=%s", (id_mov,)); conn.commit(); conn.close()
                    actualizar_saldos_en_cascada(row_to_edit['mes'])
                    st.warning("Eliminado"); st.rerun()

        elif len(selected_records) > 1:
            st.markdown("---")
            st.markdown("### 🛠️ EDICIÓN MASIVA")
            st.warning(f"Seleccionados: {len(selected_records)}")
            c_mass_1, c_mass_2, c_mass_3, c_mass_4 = st.columns(4)
            with c_mass_1:
                new_mass_date = st.date_input("Nueva Fecha de Pago", datetime.date.today())
            with c_mass_2:
                new_mass_payment = st.selectbox("Nueva Forma de Pago", OPCIONES_PAGO)
            with c_mass_3:
                mark_paid = st.checkbox("✅ Marcar TODOS como pagados")
            with c_mass_4:
                st.write("") 
                st.write("") 
                if st.button("💾 ACTUALIZAR TODO"):
                    conn = get_db_connection(); c = conn.cursor()
                    ids_to_update = tuple([int(r['id']) for r in selected_records])
                    if mark_paid:
                        c.execute("UPDATE movimientos SET fecha_pago = %s, forma_pago = %s, pagado = TRUE WHERE id IN %s", (str(new_mass_date), new_mass_payment, ids_to_update))
                    else:
                        c.execute("UPDATE movimientos SET fecha_pago = %s, forma_pago = %s WHERE id IN %s", (str(new_mass_date), new_mass_payment, ids_to_update))
                    conn.commit(); conn.close()
                    st.success("Registros actualizados"); st.rerun()
            
            st.divider()
            if st.button(f"❌ ELIMINAR SELECCIÓN", type="primary"):
                conn = get_db_connection(); c = conn.cursor()
                ids_to_delete = tuple([int(r['id']) for r in selected_records])
                c.execute("DELETE FROM movimientos WHERE id IN %s", (ids_to_delete,))
                conn.commit(); conn.close()
                actualizar_saldos_en_cascada(mes_global)
                st.success("Eliminados."); st.rerun()
    else: st.info("Sin datos.")

with tab2: # PREDICCIONES
    c1, c2 = st.columns([1,3])
    with c1:
        lottie_ai = load_lottieurl(LOTTIE_FINANCE)
        if lottie_ai: st_lottie(lottie_ai, height=150)
    with c2:
        st.header("🔮 Predicciones de Gasto")
        st.caption("Análisis predictivo 2026-2035")

    df_ai = df_all[df_all['tipo'] == 'GASTO'].copy()
    if len(df_ai) > 0:
        df_ai['monto_normalizado'] = df_ai.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        mapa_meses = {m: i+1 for i, m in enumerate(LISTA_MESES_LARGA)}
        df_ai['mes_num'] = df_ai['mes'].map(mapa_meses)
        df_ai = df_ai.dropna(subset=['mes_num']) 
        df_monthly = df_ai.groupby('mes_num')['monto_normalizado'].sum().reset_index().sort_values('mes_num')
        if len(df_monthly) >= 2:
            X = df_monthly['mes_num'].values.reshape(-1, 1)
            y = df_monthly['monto_normalizado'].values
            model = LinearRegression()
            model.fit(X, y)
            proximo_mes_num = df_monthly['mes_num'].max() + 1
            if proximo_mes_num <= len(LISTA_MESES_LARGA):
                prediccion_futura = model.predict([[proximo_mes_num]])[0]
                nombre_proximo_mes = LISTA_MESES_LARGA[int(proximo_mes_num) - 1]
                st.metric(f"Proyección {nombre_proximo_mes}", formato_moneda_visual(prediccion_futura, "ARS"))
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=[LISTA_MESES_LARGA[int(i)-1] for i in df_monthly['mes_num']], y=df_monthly['monto_normalizado'], mode='lines+markers', name='Real', line=dict(color='#ff4b4b')))
                y_pred = model.predict(X)
                fig.add_trace(go.Scatter(x=[LISTA_MESES_LARGA[int(i)-1] for i in df_monthly['mes_num']], y=y_pred, mode='lines', name='Tendencia', line=dict(dash='dot', color='gray')))
                fig.update_layout(title="Proyección", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Fin del calendario.")
        else: st.warning("Faltan datos para predecir.")
    else: st.info("Sin gastos registrados.")

with tab3: # CONFIG
    st.header("⚙️ Configuración")
    
    st.markdown("### 📤 MIGRACIÓN")
    archivo_db = st.file_uploader("Archivo .db", type=["db", "sqlite", "sqlite3"])
    if archivo_db and st.button("🔄 MIGRAR"):
        with tempfile.NamedTemporaryFile(delete=False) as tmp: tmp.write(archivo_db.getvalue()); path=tmp.name
        conn_old = sqlite3.connect(path); df_old = pd.read_sql("SELECT * FROM movimientos", conn_old); conn_old.close()
        conn_new = get_db_connection(); c = conn_new.cursor()
        for _, r in df_old.iterrows():
            c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 
                      (r['fecha'], r['mes'], r['tipo'], r['grupo'], r['tipo_gasto'], r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
        conn_new.commit(); conn_new.close(); st.success("Migrado.")

    st.divider()
    with st.expander("🏷️ GRUPOS"):
        c1, c2 = st.columns(2)
        conn = get_db_connection(); c = conn.cursor()
        with c1:
            if st.button("Crear"): c.execute("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", (st.text_input("Nuevo").upper(),)); conn.commit(); st.rerun()
        with c2:
            d_g = st.selectbox("Borrar", grupos_db)
            if st.button("Eliminar Grupo"): c.execute("DELETE FROM grupos WHERE nombre=%s", (d_g,)); conn.commit(); st.rerun()
        conn.close()

    st.divider()
    c1, c2, c3 = st.columns(3)
    m_src = c1.selectbox("Desde", LISTA_MESES_LARGA)
    m_dst = c2.selectbox("Hasta", ["TODO EL AÑO"]+LISTA_MESES_LARGA)
    if c3.button("🚀 CLONAR"):
        conn = get_db_connection(); c = conn.cursor()
        src = pd.read_sql(f"SELECT * FROM movimientos WHERE mes='{m_src}'", conn)
        targets = [m for m in LISTA_MESES_LARGA if m.split(' ')[1] == m_src.split(' ')[1]] if m_dst == "TODO EL AÑO" else [m_dst]
        for t in targets:
            if t == m_src: continue
            c.execute("DELETE FROM movimientos WHERE mes=%s", (t,))
            for _, r in src.iterrows():
                c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", 
                          (str(datetime.date.today()), t, r['tipo'], r['grupo'], r['tipo_gasto'], r['cuota'], r['monto'], r['moneda'], r['forma_pago'], r['fecha_pago']))
        conn.commit(); st.success("Clonado."); st.rerun()

# --- NUEVA PESTAÑA 4: DEUDAS Y PAGOS PARCIALES ---
with tab4:
    st.header("📉 Gestión de Deudas y Pagos Parciales")
    st.caption("Registra aquí tus deudas totales y ve pagando de a poco. Estos pagos aparecerán en tu flujo de caja mensual.")

    c_deuda1, c_deuda2 = st.columns([1, 2])
    
    conn = get_db_connection(); c = conn.cursor()
    
    with c_deuda1:
        st.subheader("➕ Nueva Deuda")
        with st.form("nueva_deuda"):
            n_deuda = st.text_input("Nombre de la Deuda (Ej: Préstamo Juan)")
            m_deuda = st.text_input("Monto Total a Deber", "0,00")
            mon_deuda = st.selectbox("Moneda", ["ARS", "USD"])
            if st.form_submit_button("Crear Deuda"):
                monto_real = procesar_monto_input(m_deuda)
                c.execute("INSERT INTO deudas (nombre_deuda, monto_total, moneda, fecha_inicio, estado) VALUES (%s, %s, %s, %s, 'ACTIVA')", 
                          (n_deuda, monto_real, mon_deuda, str(datetime.date.today())))
                conn.commit(); st.success("Deuda Creada"); st.rerun()

    with c_deuda2:
        st.subheader("📋 Mis Deudas Activas")
        deudas_df = pd.read_sql("SELECT * FROM deudas WHERE estado='ACTIVA'", conn)
        
        if not deudas_df.empty:
            for _, deuda in deudas_df.iterrows():
                with st.expander(f"{deuda['nombre_deuda']} ({formato_moneda_visual(deuda['monto_total'], deuda['moneda'])})", expanded=True):
                    # Calcular pagado
                    c.execute("""
                        SELECT id, fecha_pago, monto FROM movimientos 
                        WHERE grupo='DEUDAS' AND tipo_gasto LIKE %s AND moneda=%s
                    """, (f"%{deuda['nombre_deuda']}%", deuda['moneda']))
                    
                    pagos_realizados = c.fetchall()
                    total_pagado = sum([p[2] for p in pagos_realizados])
                    restante = deuda['monto_total'] - total_pagado
                    progreso = min(total_pagado / deuda['monto_total'], 1.0) if deuda['monto_total'] > 0 else 0
                    
                    st.progress(progreso)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total", formato_moneda_visual(deuda['monto_total'], deuda['moneda']))
                    c2.metric("Pagado", formato_moneda_visual(total_pagado, deuda['moneda']))
                    c3.metric("Falta", formato_moneda_visual(restante, deuda['moneda']))
                    
                    # HISTORIAL DE PAGOS
                    if pagos_realizados:
                        st.markdown("###### 📜 Historial de Pagos")
                        for p in pagos_realizados:
                            col_h1, col_h2, col_h3 = st.columns([2, 2, 1])
                            col_h1.write(f"📅 {p[1]}")
                            col_h2.write(f"💰 {formato_moneda_visual(p[2], deuda['moneda'])}")
                            if col_h3.button("🗑️", key=f"del_pago_{p[0]}"):
                                c.execute("DELETE FROM movimientos WHERE id=%s", (p[0],))
                                conn.commit()
                                actualizar_saldos_en_cascada(mes_global)
                                st.rerun()
                        st.markdown("---")

                    if restante <= 0:
                        st.success("¡DEUDA PAGADA!")
                        if st.button("Archivar como Pagada", key=f"arch_{deuda['id']}"):
                            c.execute("UPDATE deudas SET estado='PAGADA' WHERE id=%s", (deuda['id'],)); conn.commit(); st.rerun()
                    else:
                        st.write("**Registrar nuevo pago:**")
                        c_pago1, c_pago2 = st.columns(2)
                        monto_pago = c_pago1.text_input("Monto a Pagar", key=f"mp_{deuda['id']}")
                        forma_pago_d = c_pago2.selectbox("Forma de Pago", OPCIONES_PAGO, key=f"fp_{deuda['id']}")
                        
                        if st.button("💸 Registrar Pago", key=f"btn_{deuda['id']}"):
                            m_pago_real = procesar_monto_input(monto_pago)
                            if m_pago_real > 0:
                                concepto_pago = f"Pago parcial: {deuda['nombre_deuda']}"
                                c.execute("""INSERT INTO movimientos 
                                    (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago, pagado) 
                                    VALUES (%s, %s, 'GASTO', 'DEUDAS', %s, '', %s, %s, %s, %s, TRUE)""",
                                    (str(datetime.date.today()), mes_global, concepto_pago, m_pago_real, deuda['moneda'], forma_pago_d, str(datetime.date.today())))
                                conn.commit()
                                actualizar_saldos_en_cascada(mes_global)
                                st.balloons()
                                st.success("Pago registrado")
                                st.rerun()
                    
                    st.markdown("---")
                    if st.button("❌ ELIMINAR DEUDA", key=f"del_debt_{deuda['id']}", type="primary"):
                        c.execute("DELETE FROM deudas WHERE id=%s", (deuda['id'],))
                        conn.commit()
                        st.warning("Deuda eliminada.")
                        st.rerun()
        else:
            st.info("No tienes deudas activas.")
            
    conn.close()