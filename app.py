import streamlit as st
import pandas as pd
import requests
import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Financiero Inteligente 2026", layout="wide")

# --- FUNCIONES CORE ---
def get_dolar_rate():
    try:
        response = requests.get("https://dolarapi.com/v1/dolares/blue")
        data = response.json()
        return (data['compra'] + data['venta']) / 2
    except:
        return 1000.0  # Valor de respaldo

def load_data():
    try:
        df = pd.read_csv("finanzas_2026.csv")
        df['fecha'] = pd.to_datetime(df['fecha'])
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=["fecha", "mes", "tipo", "grupo", "descripcion", "monto", "moneda"])

# --- INICIALIZACIÓN ---
if 'data' not in st.session_state:
    st.session_state.data = load_data()

dolar_hoy = get_dolar_rate()
meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# --- SIDEBAR: CARGA DE DATOS ---
st.sidebar.header("📥 Carga de Movimientos 2026")
with st.sidebar.form("input_form", clear_on_submit=True):
    mes_sel = st.selectbox("Mes", meses)
    tipo = st.selectbox("Tipo", ["Ganancia", "Gasto", "Ahorro"])
    grupo = st.text_input("Grupo (ej: Supermercado, Alquiler, Sueldo)")
    desc = st.text_input("Descripción corta")
    monto = st.number_input("Monto", min_value=0.0, format="%.2f")
    moneda = st.radio("Moneda", ["ARS", "USD"])
    
    if st.form_submit_button("Cargar"):
        nueva_fila = {
            "fecha": datetime.datetime.now(),
            "mes": mes_sel,
            "tipo": tipo,
            "grupo": grupo.upper(),
            "descripcion": desc,
            "monto": monto,
            "moneda": moneda
        }
        st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame([nueva_fila])], ignore_index=True)
        st.session_state.data.to_csv("finanzas_2026.csv", index=False)
        st.success("Cargado correctamente")

# --- DASHBOARD PRINCIPAL ---
st.title("🚀 Smart Finance Dashboard 2026")
st.info(f"💵 Cotización promedio Dólar Blue: **${dolar_hoy}**")

# --- LÓGICA DE CÁLCULO ---
df = st.session_state.data.copy()
# Normalizar a ARS para cálculos de balance
df['monto_ars'] = df.apply(lambda x: x['monto'] * dolar_hoy if x['moneda'] == 'USD' else x['monto'], axis=1)

def calcular_balance_mes(mes_nombre):
    mes_data = df[df['mes'] == mes_nombre]
    ganancias = mes_data[mes_data['tipo'] == "Ganancia"]['monto_ars'].sum()
    gastos = mes_data[mes_data['tipo'] == "Gasto"]['monto_ars'].sum()
    ahorros = mes_data[mes_data['tipo'] == "Ahorro"]['monto_ars'].sum()
    return ganancias - gastos - ahorros

# Generar balances mensuales secuenciales
balances = {}
acumulado = 0.0
for m in meses:
    mes_neto = calcular_balance_mes(m)
    acumulado += mes_neto
    balances[m] = acumulado

# --- VISUALIZACIÓN ---
col1, col2, col3 = st.columns(3)
mes_actual = st.selectbox("Ver análisis detallado de:", meses)

with col1:
    balance_actual = balances[mes_actual]
    st.metric("Balance Acumulado", f"${balance_actual:,.2f} ARS")

with col2:
    idx_siguiente = (meses.index(mes_actual) + 1) % 12
    mes_sig = meses[idx_siguiente]
    # Predicción simple basada en promedio de gastos previos
    promedio_gastos = df[df['tipo'] == "Gasto"]['monto_ars'].mean() if not df.empty else 0
    st.metric(f"Predicción {mes_sig}", f"${(balance_actual - promedio_gastos):,.2f} ARS", delta="- Gastos estimados")

with col3:
    st.metric("Poder de ahorro (USD)", f"US$ {balance_actual/dolar_hoy:,.2f}")

# --- TABLA DE GRUPOS ---
st.subheader(f"📊 Desglose por Grupos - {mes_actual}")
if not df[df['mes'] == mes_actual].empty:
    gr_df = df[df['mes'] == mes_actual].groupby(['grupo', 'tipo'])['monto_ars'].sum().reset_index()
    st.table(gr_df.style.format({"monto_ars": "${:,.2f}"}))
else:
    st.write("Sin datos para este mes.")