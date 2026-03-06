import streamlit as st
import pandas as pd
import datetime
from config import OPCIONES_PAGO
from utils import formato_moneda_visual, procesar_monto_input
from db import db_connection


def render(mes_global):
    st.header("📉 Deudas"); c1,c2=st.columns([1,2])
    with db_connection() as conn:
        c=conn.cursor()
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
                        st.success("Pagada")
                        if st.button("Archivar", key=f"a{d['id']}"): c.execute("UPDATE deudas SET estado='PAGADA' WHERE id=%s",(d['id'],));conn.commit();st.rerun()
                    else:
                        c1_d,c2_d=st.columns(2); m_d=c1_d.text_input("Monto",key=f"m{d['id']}"); p_d=c2_d.selectbox("Pago",OPCIONES_PAGO,key=f"p{d['id']}")
                        if st.button("Pagar",key=f"b{d['id']}"): c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,cuota,monto,moneda,forma_pago,fecha_pago,pagado) VALUES (%s,%s,'GASTO','DEUDAS',%s,'',%s,%s,%s,%s,TRUE)",(str(datetime.date.today()),mes_global,f"Pago: {d['nombre_deuda']}",procesar_monto_input(m_d),d['moneda'],p_d,str(datetime.date.today())));conn.commit();st.rerun()

                    # --- HISTORIAL DE PAGOS ---
                    df_hist = pd.read_sql(
                        "SELECT fecha, monto, moneda, forma_pago, mes FROM movimientos WHERE grupo='DEUDAS' AND tipo_gasto LIKE %s ORDER BY fecha DESC",
                        conn, params=(f"%{d['nombre_deuda']}%",)
                    )
                    if not df_hist.empty:
                        with st.expander(f"📋 Historial ({len(df_hist)} pagos)", expanded=False):
                            df_hist_show = df_hist.copy()
                            df_hist_show['monto'] = df_hist_show.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
                            st.dataframe(
                                df_hist_show[['fecha', 'monto', 'forma_pago', 'mes']].rename(columns={
                                    'fecha': 'Fecha', 'monto': 'Monto', 'forma_pago': 'Forma Pago', 'mes': 'Mes'
                                }),
                                hide_index=True, use_container_width=True
                            )

                    if st.button("Eliminar",key=f"e{d['id']}"):
                        st.session_state[f'confirmar_del_deuda_{d["id"]}'] = True

                    if st.session_state.get(f'confirmar_del_deuda_{d["id"]}'):
                        st.warning(f"¿Seguro que queres eliminar la deuda **{d['nombre_deuda']}**?")
                        cd1, cd2 = st.columns(2)
                        if cd1.button("Si, eliminar", key=f"conf_deuda_si_{d['id']}"):
                            c.execute("DELETE FROM deudas WHERE id=%s",(d['id'],));conn.commit()
                            st.session_state.pop(f'confirmar_del_deuda_{d["id"]}', None); st.rerun()
                        if cd2.button("Cancelar", key=f"conf_deuda_no_{d['id']}"):
                            st.session_state.pop(f'confirmar_del_deuda_{d["id"]}', None); st.rerun()
