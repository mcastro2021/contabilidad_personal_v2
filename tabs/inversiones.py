import streamlit as st
import pandas as pd
import datetime
from utils import formato_moneda_visual, procesar_monto_input
from db import db_connection


def render(dolar_val):
    st.header("💰 Inversiones")
    with db_connection() as conn:
        df_inv = pd.read_sql("SELECT * FROM inversiones WHERE estado='ACTIVA' ORDER BY fecha_inicio DESC", conn)

    with st.form("nueva_inversion"):
        st.subheader("➕ Nueva Inversión")
        ci1, ci2 = st.columns(2)
        tipo_inv = ci1.selectbox("Tipo", ["Plazo Fijo", "FCI", "Cripto", "Acciones", "Bono", "Otro"])
        entidad_inv = ci2.text_input("Entidad / Banco")
        ci3, ci4, ci5 = st.columns(3)
        monto_inv = ci3.text_input("Monto Inicial", "0,00")
        moneda_inv = ci4.selectbox("Moneda", ["ARS", "USD"])
        tna_inv = ci5.number_input("TNA (%)", 0.0, 50000.0, 0.0, step=0.5)
        ci6, ci7 = st.columns(2)
        plazo_inv = ci6.number_input("Plazo (días)", 1, 3650, 30)
        fecha_inv = ci7.date_input("Fecha Inicio", datetime.date.today())
        if st.form_submit_button("💾 Agregar Inversión"):
            with db_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT INTO inversiones (tipo, entidad, monto_inicial, tna, fecha_inicio, plazo_dias, estado) VALUES (%s,%s,%s,%s,%s,%s,'ACTIVA')",
                          (tipo_inv, entidad_inv, procesar_monto_input(monto_inv), tna_inv, str(fecha_inv), int(plazo_inv)))
                conn.commit()
            st.success("Inversión agregada"); st.rerun()

    st.divider()
    if df_inv.empty:
        st.info("No hay inversiones activas registradas.")
    else:
        hoy_inv = datetime.date.today()
        total_capital = 0.0; total_ganancia = 0.0
        for _, inv in df_inv.iterrows():
            moneda_i = "ARS"
            ganancia = inv['monto_inicial'] * (inv['tna'] / 100) * (inv['plazo_dias'] / 365) if inv['tna'] > 0 else 0.0
            total_capital += inv['monto_inicial'] * (dolar_val if moneda_i == 'USD' else 1)
            total_ganancia += ganancia * (dolar_val if moneda_i == 'USD' else 1)
            try:
                fecha_fin_inv = (pd.to_datetime(inv['fecha_inicio']) + datetime.timedelta(days=int(inv['plazo_dias']))).date()
                dias_rest = (fecha_fin_inv - hoy_inv).days
            except:
                fecha_fin_inv = None; dias_rest = None
            vencida = dias_rest is not None and dias_rest < 0
            emoji = "⏰" if vencida else "🔄"
            with st.expander(f"{emoji} {inv['tipo']} — {inv['entidad']}  |  Capital: {formato_moneda_visual(inv['monto_inicial'], 'ARS')}  |  TNA: {inv['tna']}%", expanded=True):
                ki1, ki2, ki3, ki4 = st.columns(4)
                ki1.metric("Capital", formato_moneda_visual(inv['monto_inicial'], 'ARS'))
                ki2.metric("Ganancia Est.", formato_moneda_visual(ganancia, 'ARS'))
                ki3.metric("Total Est.", formato_moneda_visual(inv['monto_inicial'] + ganancia, 'ARS'))
                ki4.metric("Vencimiento", str(fecha_fin_inv) if fecha_fin_inv else "N/A",
                           delta=f"{'Vencida hace' if vencida else 'Faltan'} {abs(dias_rest)} días" if dias_rest is not None else "")
                ka1, ka2 = st.columns(2)
                if ka1.button("Archivar como Cobrada", key=f"arch_inv_{inv['id']}"):
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("UPDATE inversiones SET estado='VENCIDA' WHERE id=%s", (inv['id'],))
                        conn.commit()
                    st.rerun()
                if ka2.button("Eliminar", key=f"del_inv_{inv['id']}"):
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM inversiones WHERE id=%s", (inv['id'],))
                        conn.commit()
                    st.rerun()
        st.divider()
        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Total Capital (ARS)", formato_moneda_visual(total_capital, 'ARS'))
        sm2.metric("Total Ganancia Est. (ARS)", formato_moneda_visual(total_ganancia, 'ARS'))
        sm3.metric("Total Portafolio (ARS)", formato_moneda_visual(total_capital + total_ganancia, 'ARS'))
