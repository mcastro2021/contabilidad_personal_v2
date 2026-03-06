import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from config import LISTA_MESES_LARGA
from utils import formato_moneda_visual


def render(df_all):
    st.header("🔮 Predicciones de Tendencia")
    if df_all.empty:
        st.info("No hay datos suficientes para hacer predicciones.")
        return

    df_pred = df_all[df_all['moneda'] == 'ARS'].copy()
    df_pred['mes_idx'] = df_pred['mes'].apply(lambda m: LISTA_MESES_LARGA.index(m) if m in LISTA_MESES_LARGA else -1)
    df_pred = df_pred[df_pred['mes_idx'] >= 0]
    monthly = df_pred.groupby(['mes_idx', 'mes']).apply(
        lambda g: pd.Series({
            'ganancias': g[g['tipo'] == 'GANANCIA']['monto'].sum(),
            'gastos': g[g['tipo'] == 'GASTO']['monto'].sum(),
        })
    ).reset_index().sort_values('mes_idx')
    monthly['saldo'] = monthly['ganancias'] - monthly['gastos']

    if len(monthly) < 2:
        st.warning("Se necesitan al menos 2 meses de datos historicos en ARS para generar predicciones.")
        return

    X = monthly['mes_idx'].values.reshape(-1, 1)
    pc1, pc2 = st.columns(2)
    n_fut = pc1.slider("Meses a predecir:", 3, 12, 6)
    modelo_tipo = pc2.selectbox("Modelo", ["Lineal", "Polinomico (grado 2)", "Polinomico (grado 3)"])

    last_idx = int(monthly['mes_idx'].max())
    future_idx = [i for i in range(last_idx + 1, last_idx + n_fut + 1) if i < len(LISTA_MESES_LARGA)]
    future_meses = [LISTA_MESES_LARGA[i] for i in future_idx]
    X_future = np.array(future_idx).reshape(-1, 1)
    pred_data = {'mes': future_meses}

    for col in ['ganancias', 'gastos', 'saldo']:
        if modelo_tipo == "Lineal":
            model = LinearRegression()
        elif modelo_tipo == "Polinomico (grado 2)":
            model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())
        else:
            model = make_pipeline(PolynomialFeatures(degree=3), LinearRegression())
        model.fit(X, monthly[col].values)
        pred_data[col] = np.maximum(model.predict(X_future), 0)

    df_future = pd.DataFrame(pred_data)
    modelo_label = modelo_tipo.replace("Polinomico", "Polinómica")

    fig_pred = go.Figure()
    fig_pred.add_trace(go.Bar(x=monthly['mes'], y=monthly['ganancias'], name='Ganancias Historicas', marker_color='#28a745', opacity=0.8))
    fig_pred.add_trace(go.Bar(x=monthly['mes'], y=monthly['gastos'], name='Gastos Historicos', marker_color='#dc3545', opacity=0.8))
    fig_pred.add_trace(go.Scatter(x=df_future['mes'], y=df_future['ganancias'], name='Pred. Ganancias', mode='lines+markers', line=dict(dash='dash', color='#28a745', width=2)))
    fig_pred.add_trace(go.Scatter(x=df_future['mes'], y=df_future['gastos'], name='Pred. Gastos', mode='lines+markers', line=dict(dash='dash', color='#dc3545', width=2)))
    fig_pred.add_trace(go.Scatter(x=df_future['mes'], y=df_future['saldo'], name='Pred. Saldo', mode='lines+markers', line=dict(dash='dot', color='#ffc107', width=2)))
    fig_pred.update_layout(barmode='group', title=f"Historico + Prediccion (Regresion {modelo_label} — ARS)")
    st.plotly_chart(fig_pred, use_container_width=True)

    st.subheader("Tabla de predicciones")
    df_show = df_future.copy()
    df_show.columns = ['Mes', 'Ganancias Est.', 'Gastos Est.', 'Saldo Est.']
    df_show['Ganancias Est.'] = df_show['Ganancias Est.'].apply(lambda v: formato_moneda_visual(v, 'ARS'))
    df_show['Gastos Est.'] = df_show['Gastos Est.'].apply(lambda v: formato_moneda_visual(v, 'ARS'))
    df_show['Saldo Est.'] = df_show['Saldo Est.'].apply(lambda v: formato_moneda_visual(v, 'ARS'))
    st.dataframe(df_show, hide_index=True, use_container_width=True)

    st.caption(f"⚠️ Predicciones basadas en regresion {modelo_label.lower()} historica. No constituyen asesoramiento financiero.")
