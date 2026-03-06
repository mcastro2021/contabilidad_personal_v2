import streamlit as st
import pandas as pd
import os
import datetime
import plotly.express as px
import plotly.graph_objects as go
import logging
import numpy as np
from dotenv import load_dotenv
from streamlit_lottie import st_lottie

from config import (
    LISTA_MESES_LARGA, MESES_NOMBRES, INDICE_MES_ACTUAL,
    OPCIONES_PAGO, LOTTIE_FINANCE
)
from db import db_connection, init_db
from auth import login_screen
from utils import (
    load_lottieurl, formato_moneda_visual, procesar_monto_input,
    enviar_notificacion
)
from logic import automatizaciones, actualizar_saldos, get_dolar, calcular_monto_salario_mes
from tabs import dashboard, inversiones, predicciones, configuracion, deudas

# --- IMPORTACION SEGURA DE IA ---
try:
    import google.generativeai as genai
    HAS_AI = True
except ImportError:
    HAS_AI = False

# --- CONFIGURACION DE LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# --- CARGAR VARIABLES ---
load_dotenv()

# --- CONFIGURACION DE PAGINA ---
st.set_page_config(page_title="CONTABILIDAD PERSONAL V5 (IA)", layout="wide")

# --- INIT DB ---
init_db()

# --- LOGIN ---
login_screen()

# ==========================================
# APP
# ==========================================
dolar_val, dolar_info = get_dolar()
automatizaciones()
with db_connection() as conn:
    grupos_db = pd.read_sql("SELECT nombre FROM grupos ORDER BY nombre ASC", conn)['nombre'].tolist()
    df_all = pd.read_sql("SELECT * FROM movimientos", conn)

with st.sidebar:
    lottie = load_lottieurl(LOTTIE_FINANCE)
    if lottie: st_lottie(lottie, height=100)
    st.write(f"👤 **{st.session_state['username']}**")
    if st.button("Salir"): st.session_state['logged_in'] = False; st.rerun()
    st.divider()

    st.header("📅 Configuración")
    mes_global = st.selectbox("Mes de Trabajo:", LISTA_MESES_LARGA, index=INDICE_MES_ACTUAL)

    st.divider()

    # --- LOGICA DE FECHAS DINAMICA ---
    partes = mes_global.split(" ")
    nombre_mes_seleccionado = partes[0]
    anio_seleccionado = int(partes[1])
    mes_num_seleccionado = MESES_NOMBRES.index(nombre_mes_seleccionado) + 1

    hoy_real = datetime.date.today()

    if hoy_real.month == mes_num_seleccionado and hoy_real.year == anio_seleccionado:
        fecha_default = hoy_real
    else:
        fecha_default = datetime.date(anio_seleccionado, mes_num_seleccionado, 1)

    st.header("📥 Cargar Nuevo")
    with st.form("alta_movimiento"):
        mes_carga = st.selectbox("📅 MES:", LISTA_MESES_LARGA, index=LISTA_MESES_LARGA.index(mes_global))
        t_sel = st.selectbox("TIPO", ["GASTO", "GANANCIA"])
        g_sel = st.selectbox("GRUPO", grupos_db)
        c_con, c_cont = st.columns(2)
        con = c_con.text_input("CONCEPTO"); cont = c_cont.text_input("CUENTA O CONTRATO")
        c1, c2 = st.columns(2); c_act = c1.number_input("Cuota", 1, 300, 1); c_tot = c2.number_input("Total", 1, 300, 1)
        m_inp = st.text_input("MONTO", "0,00"); mon = st.radio("MONEDA", ["ARS", "USD"], horizontal=True)
        pag = st.selectbox("PAGO", OPCIONES_PAGO); fec = st.date_input("FECHA", fecha_default)
        ya = st.checkbox("¿Pagado?")

        if st.form_submit_button("GRABAR"):
            mf = procesar_monto_input(m_inp); idx = LISTA_MESES_LARGA.index(mes_carga)
            with db_connection() as conn:
                c = conn.cursor()
                if c_tot == 1:
                    vc = calcular_monto_salario_mes(mes_carga)
                    mg = vc if (con.strip().upper() == "SALARIO CHICOS" and vc) else mf
                    c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,'',%s,%s,%s,%s,%s)", (str(datetime.date.today()), mes_carga, t_sel, g_sel, con, cont, mg, mon, pag, str(fec), ya))
                else:
                    for i in range(int(c_act), int(c_tot)+1):
                        off = i - int(c_act)
                        if idx + off < len(LISTA_MESES_LARGA):
                            mt = LISTA_MESES_LARGA[idx + off]; vc = calcular_monto_salario_mes(mt)
                            mg = vc if (con.strip().upper() == "SALARIO CHICOS" and vc) else mf
                            c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, contrato, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()), mt, t_sel, g_sel, con, cont, f"{i}/{c_tot}", mg, mon, pag, (fec + datetime.timedelta(days=30*off)).strftime('%Y-%m-%d'), ya if off==0 else False))
                conn.commit()
            actualizar_saldos(mes_carga)
            enviar_notificacion("Nuevo", f"{con} ({mf})"); st.success("Guardado"); st.rerun()

    st.divider()

    with st.expander("🤖 Asistente IA (Chat)", expanded=False):
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key: st.warning("Falta API Key")
        elif not HAS_AI: st.error("Falta librería IA")
        else:
            try:
                genai.configure(api_key=api_key)
                models_list = []
                try:
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods: models_list.append(m.name)
                except: pass
                if not models_list: model_name = 'models/gemini-1.5-flash'
                else: model_name = next((m for m in ['models/gemini-1.5-flash', 'models/gemini-pro'] if m in models_list), models_list[0])
                st.caption(f"🧠 {model_name.split('/')[-1]}")
                model = genai.GenerativeModel(model_name)
                with st.form(key="chat_ia_form"):
                    pregunta = st.text_input("Pregunta:", key="q_ia_sb")
                    if st.form_submit_button("Enviar") and pregunta:
                        with st.spinner("..."):
                            try:
                                df_chat = df_all.copy()
                                info = ", ".join([f"{c} ({t})" for c, t in zip(df_chat.columns, df_chat.dtypes)])
                                prompt = f"""Contexto: Finanzas Arg ($). DF: {info}. User: "{pregunta}".
                                Instrucciones: 1. Python code only. 2. Búsqueda Regex (ej: 'poll' -> 'pollo/s'). 3. Suma montos. 4. Output: `resultado_texto`(str), `figura_plotly`(px). 5. No print."""
                                resp = model.generate_content(prompt).text.replace("```python", "").replace("```", "").strip()
                                safe_builtins = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in
                                    ['abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'filter', 'float', 'format',
                                     'int', 'isinstance', 'len', 'list', 'map', 'max', 'min', 'print', 'range',
                                     'round', 'set', 'sorted', 'str', 'sum', 'tuple', 'type', 'zip'] if hasattr(__builtins__, k) or (isinstance(__builtins__, dict) and k in __builtins__)}
                                safe_globals = {"__builtins__": safe_builtins, "pd": pd, "px": px, "go": go, "np": np}
                                loc = {"df_chat": df_chat}
                                exec(resp, safe_globals, loc)
                                if "resultado_texto" in loc: st.info(loc["resultado_texto"])
                                if "figura_plotly" in loc and isinstance(loc["figura_plotly"], go.Figure): st.plotly_chart(loc["figura_plotly"], use_container_width=True)
                            except Exception as e: st.error(f"Error: {e}")
            except Exception as e: st.error(f"Error IA: {e}")

st.title("CONTABILIDAD PERSONAL V5")
df_filtrado = df_all[df_all['mes'] == mes_global].copy()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 DASHBOARD", "💰 INVERSIONES", "🔮 PREDICCIONES", "⚙️ CONFIGURACIÓN", "📉 DEUDAS"])

with tab1:
    dashboard.render(df_all, df_filtrado, dolar_val, dolar_info, mes_global, grupos_db)

with tab2:
    inversiones.render(dolar_val)

with tab3:
    predicciones.render(df_all)

with tab4:
    configuracion.render(grupos_db)

with tab5:
    deudas.render(mes_global)
