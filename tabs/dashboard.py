import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import datetime
import calendar
from config import COLOR_MAP, OPCIONES_PAGO, MESES_NOMBRES, LISTA_MESES_LARGA
from utils import formato_moneda_visual, generar_alertas, procesar_monto_input
from logic import actualizar_saldos
from db import db_connection


def render(df_all, df_filtrado, dolar_val, dolar_info, mes_global, grupos_db):
    alertas, t_vencido, t_vencer, t_cobrar = generar_alertas(df_all, dolar_val)
    if alertas:
        with st.expander(f"🔔 Tienes {len(alertas)} Avisos Importantes", expanded=True):
            for a in alertas:
                if "VENCIDO" in a: st.error(a)
                elif "Cobras" in a or "Cobro Atrasado" in a: st.success(a)
                else: st.warning(a)
            st.markdown("---")
            k1, k2, k3 = st.columns(3)
            k1.metric("🔴 Total Vencido", formato_moneda_visual(t_vencido, "ARS"))
            k2.metric("⚠️ Total a Vencer", formato_moneda_visual(t_vencer, "ARS"))
            k3.metric("💵 Total a Cobrar", formato_moneda_visual(t_cobrar, "ARS"))

    st.info(f"Dolar Blue: {formato_moneda_visual(dolar_val, 'ARS')} {dolar_info}")

    if not df_filtrado.empty:
        r_ars = df_filtrado[(df_filtrado['moneda']=="ARS")&(df_filtrado['tipo']=="GANANCIA")]['monto'].sum() - df_filtrado[(df_filtrado['moneda']=="ARS")&(df_filtrado['tipo']=="GASTO")]['monto'].sum()
        r_usd = df_filtrado[(df_filtrado['moneda']=="USD")&(df_filtrado['tipo']=="GANANCIA")]['monto'].sum() - df_filtrado[(df_filtrado['moneda']=="USD")&(df_filtrado['tipo']=="GASTO")]['monto'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("RESULTADO (ARS)", formato_moneda_visual(r_ars, "ARS"))
        c2.metric("RESULTADO (USD)", formato_moneda_visual(r_usd, "USD"))
        c3.metric("PATRIMONIO", formato_moneda_visual(r_ars + (r_usd * dolar_val), "ARS"))
        st.divider()

        df_filtrado['m_ars_v'] = df_filtrado.apply(lambda x: x['monto'] * dolar_val if x['moneda'] == 'USD' else x['monto'], axis=1)
        c_g1, c_g2 = st.columns(2)

        with c_g1:
            st.caption("Distribución de Gastos (Click para filtrar)")
            df_gastos = df_filtrado[df_filtrado['tipo']=="GASTO"]
            if not df_gastos.empty:
                fig_pie = px.pie(df_gastos, values='m_ars_v', names='grupo', hole=0.4)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                sel_pie = st.plotly_chart(fig_pie, on_select="rerun", selection_mode="points", use_container_width=True)
                filtro_grupo = sel_pie["selection"]["points"][0]["label"] if sel_pie and sel_pie["selection"]["points"] else None
                if filtro_grupo: st.warning(f"📂 Filtrando por Grupo: {filtro_grupo}")
            else: filtro_grupo = None

        with c_g2:
            st.caption("Flujo de Caja")
            if not df_filtrado.empty:
                st.plotly_chart(px.bar(df_filtrado.groupby(['moneda', 'tipo'])['monto'].sum().reset_index(), x='moneda', y='monto', color='tipo', barmode='group', color_discrete_map=COLOR_MAP), use_container_width=True)

        # --- MAPA DE CALOR CALENDARIO + GASTOS POR FORMA DE PAGO ---
        c_h1, c_h2 = st.columns(2)

        with c_h1:
            st.caption("📅 Mapa de Calor de Gastos")
            df_gastos_cal = df_filtrado[df_filtrado['tipo'] == 'GASTO'].copy()
            if not df_gastos_cal.empty:
                partes_mes = mes_global.split(" ")
                mes_num = MESES_NOMBRES.index(partes_mes[0]) + 1
                anio_num = int(partes_mes[1])
                num_dias = calendar.monthrange(anio_num, mes_num)[1]
                primer_dia_semana = calendar.monthrange(anio_num, mes_num)[0]

                df_gastos_cal['fecha_dt'] = pd.to_datetime(df_gastos_cal['fecha_pago'], errors='coerce')
                df_gastos_cal['dia'] = df_gastos_cal['fecha_dt'].dt.day
                gasto_por_dia = df_gastos_cal.groupby('dia')['m_ars_v'].sum().to_dict()

                semanas = []
                semana_actual = [None] * primer_dia_semana
                for dia in range(1, num_dias + 1):
                    semana_actual.append(dia)
                    if len(semana_actual) == 7:
                        semanas.append(semana_actual)
                        semana_actual = []
                if semana_actual:
                    semana_actual.extend([None] * (7 - len(semana_actual)))
                    semanas.append(semana_actual)

                z_vals = []
                text_vals = []
                for semana in semanas:
                    z_row = []
                    text_row = []
                    for dia in semana:
                        if dia is None:
                            z_row.append(np.nan)
                            text_row.append("")
                        else:
                            gasto = gasto_por_dia.get(dia, 0)
                            z_row.append(gasto)
                            text_row.append(f"Día {dia}<br>{formato_moneda_visual(gasto, 'ARS')}" if gasto > 0 else f"Día {dia}<br>Sin gastos")
                    z_vals.append(z_row)
                    text_vals.append(text_row)

                fig_cal = go.Figure(data=go.Heatmap(
                    z=z_vals,
                    x=["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                    y=[f"Sem {i+1}" for i in range(len(semanas))],
                    text=text_vals,
                    hoverinfo="text",
                    colorscale=[[0, "#1a1a2e"], [0.5, "#e74c3c"], [1, "#ff0000"]],
                    showscale=True,
                    colorbar=dict(title="$ ARS"),
                    xgap=3, ygap=3
                ))
                for i, semana in enumerate(semanas):
                    for j, dia in enumerate(semana):
                        if dia is not None:
                            fig_cal.add_annotation(
                                x=j, y=i, text=str(dia),
                                showarrow=False, font=dict(color="white", size=11)
                            )
                fig_cal.update_layout(
                    height=250, margin=dict(l=10, r=10, t=10, b=10),
                    yaxis=dict(autorange="reversed", showticklabels=False),
                    xaxis=dict(side="top")
                )
                st.plotly_chart(fig_cal, use_container_width=True)
            else:
                st.info("No hay gastos para mostrar en el calendario.")

        with c_h2:
            st.caption("💳 Gastos por Forma de Pago")
            if not df_gastos.empty:
                df_fp = df_gastos.groupby('forma_pago')['m_ars_v'].sum().reset_index()
                df_fp.columns = ['Forma de Pago', 'Total']
                df_fp = df_fp.sort_values('Total', ascending=True)
                fig_fp = px.bar(df_fp, x='Total', y='Forma de Pago', orientation='h',
                                color='Total', color_continuous_scale='Reds')
                fig_fp.update_layout(
                    height=250, margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False, coloraxis_showscale=False
                )
                fig_fp.update_traces(
                    text=df_fp['Total'].apply(lambda v: formato_moneda_visual(v, 'ARS')),
                    textposition='auto'
                )
                st.plotly_chart(fig_fp, use_container_width=True)
            else:
                st.info("No hay gastos para mostrar por forma de pago.")

        # --- PRESUPUESTOS POR GRUPO ---
        with db_connection() as conn:
            try:
                df_pres = pd.read_sql("SELECT * FROM presupuestos", conn)
            except:
                df_pres = pd.DataFrame()
        if not df_pres.empty and not df_gastos.empty:
            st.caption("📊 Presupuestos por Grupo")
            gastos_grupo = df_gastos.groupby('grupo')['m_ars_v'].sum().to_dict()
            cols_pres = st.columns(min(len(df_pres), 4))
            for idx, (_, p) in enumerate(df_pres.iterrows()):
                with cols_pres[idx % len(cols_pres)]:
                    gastado = gastos_grupo.get(p['grupo'], 0)
                    limite = p['limite']
                    pct = min(gastado / limite, 1.0) if limite > 0 else 0
                    color = "🟢" if pct < 0.8 else ("🟡" if pct < 1.0 else "🔴")
                    st.markdown(f"**{color} {p['grupo']}**")
                    st.progress(pct)
                    st.caption(f"{formato_moneda_visual(gastado, 'ARS')} / {formato_moneda_visual(limite, 'ARS')}")
                    if pct >= 0.8 and pct < 1.0:
                        st.warning(f"Cerca del limite ({pct:.0%})")
                    elif pct >= 1.0:
                        st.error(f"Excedido ({formato_moneda_visual(gastado - limite, 'ARS')} de mas)")

        # --- EVOLUCION PATRIMONIAL ---
        with st.expander("📈 Evolución Patrimonial", expanded=False):
            if not df_all.empty:
                meses_con_datos = sorted(df_all['mes'].unique(), key=lambda m: LISTA_MESES_LARGA.index(m) if m in LISTA_MESES_LARGA else 999)
                evol_data = []
                for m in meses_con_datos:
                    if m not in LISTA_MESES_LARGA: continue
                    dfm = df_all[df_all['mes'] == m]
                    g_ars = dfm[(dfm['moneda']=='ARS')&(dfm['tipo']=='GANANCIA')]['monto'].sum()
                    e_ars = dfm[(dfm['moneda']=='ARS')&(dfm['tipo']=='GASTO')]['monto'].sum()
                    g_usd = dfm[(dfm['moneda']=='USD')&(dfm['tipo']=='GANANCIA')]['monto'].sum()
                    e_usd = dfm[(dfm['moneda']=='USD')&(dfm['tipo']=='GASTO')]['monto'].sum()
                    saldo_ars = g_ars - e_ars
                    saldo_usd = g_usd - e_usd
                    patrimonio = saldo_ars + (saldo_usd * dolar_val)
                    evol_data.append({'mes': m, 'Saldo ARS': saldo_ars, 'Saldo USD (conv.)': saldo_usd * dolar_val, 'Patrimonio': patrimonio})
                if evol_data:
                    df_evol = pd.DataFrame(evol_data)
                    fig_evol = go.Figure()
                    fig_evol.add_trace(go.Scatter(x=df_evol['mes'], y=df_evol['Patrimonio'], name='Patrimonio', mode='lines+markers', line=dict(color='#ffc107', width=3), fill='tozeroy', fillcolor='rgba(255,193,7,0.1)'))
                    fig_evol.add_trace(go.Bar(x=df_evol['mes'], y=df_evol['Saldo ARS'], name='Saldo ARS', marker_color='#28a745', opacity=0.6))
                    fig_evol.update_layout(title="Evolución Patrimonial Mensual", barmode='overlay', height=350)
                    st.plotly_chart(fig_evol, use_container_width=True)

        # --- FILTROS DE BUSQUEDA ---
        st.markdown("---")
        with st.expander("🔍 Filtros", expanded=False):
            fc1, fc2, fc3, fc4 = st.columns(4)
            busqueda = fc1.text_input("Buscar concepto", key="dash_busqueda")
            filtro_moneda = fc2.selectbox("Moneda", ["Todas", "ARS", "USD"], key="dash_moneda")
            filtro_fpago = fc3.selectbox("Forma de Pago", ["Todas"] + OPCIONES_PAGO, key="dash_fpago")
            filtro_estado = fc4.selectbox("Estado", ["Todos", "Pagado", "Pendiente"], key="dash_estado")

        df_tabla = df_filtrado.copy()
        if filtro_grupo: df_tabla = df_tabla[df_tabla['grupo'] == filtro_grupo]
        if busqueda: df_tabla = df_tabla[df_tabla['tipo_gasto'].str.contains(busqueda, case=False, na=False)]
        if filtro_moneda != "Todas": df_tabla = df_tabla[df_tabla['moneda'] == filtro_moneda]
        if filtro_fpago != "Todas": df_tabla = df_tabla[df_tabla['forma_pago'] == filtro_fpago]
        if filtro_estado == "Pagado": df_tabla = df_tabla[df_tabla['pagado'] == True]
        elif filtro_estado == "Pendiente": df_tabla = df_tabla[df_tabla['pagado'] != True]

        df_tabla['monto_vis'] = df_tabla.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
        df_tabla['pagado'] = df_tabla['pagado'].fillna(False).astype(bool)
        df_tabla['estado'] = df_tabla['pagado'].apply(lambda x: "✅" if x else "⏳")

        cols = ["estado", "tipo_gasto", "contrato", "monto_vis", "cuota", "forma_pago", "fecha_pago", "pagado"]
        cfg = {
            "estado": st.column_config.TextColumn("Estado", width="small"),
            "tipo_gasto": st.column_config.TextColumn("Tipo de Gasto"),
            "contrato": st.column_config.TextColumn("Contrato"),
            "monto_vis": st.column_config.TextColumn("Monto"),
            "cuota": st.column_config.TextColumn("Cuota"),
            "forma_pago": st.column_config.TextColumn("Forma de Pago"),
            "fecha_pago": st.column_config.DateColumn("Fecha de Pago", format="DD/MM/YYYY"),
            "pagado": st.column_config.CheckboxColumn("Pagado")
        }

        def style_fn(row): return ['background-color: #1c3323' if row['pagado'] else ''] * len(row)
        selected = []

        for gt in ["GANANCIA", "GASTO"]:
            dft = df_tabla[df_tabla['tipo'] == gt]
            if not dft.empty:
                st.markdown(f"## {('🟢' if gt=='GANANCIA' else '🔴')} {gt}S")
                for grp in sorted(dft['grupo'].unique()):
                    with st.container():
                        st.subheader(f"📂 {grp}")
                        dfg = dft[dft['grupo'] == grp].sort_values(by=['pagado', 'fecha_pago'], ascending=[True, True])
                        s = st.dataframe(dfg[cols].style.apply(style_fn, axis=1), column_config=cfg, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"t_{gt}_{grp}")
                        st.markdown(f"**📉 Total {grp}: {formato_moneda_visual(dfg['m_ars_v'].sum(), 'ARS')}**")
                        if s.selection.rows:
                            for i in s.selection.rows: selected.append(dfg.iloc[i])

        if len(selected) == 1:
            r = selected[0]; idm = int(r['id'])
            st.markdown(f"### ✏️ Editar: {r['tipo_gasto']}")
            with st.form("edit"):
                c1,c2,c3,c4 = st.columns(4)
                nt = c1.selectbox("Tipo", ["GASTO", "GANANCIA"], index=["GASTO", "GANANCIA"].index(r['tipo']))
                ng = c2.selectbox("Grupo", grupos_db, index=grupos_db.index(r['grupo']) if r['grupo'] in grupos_db else 0)
                nc = c3.text_input("Concepto", value=r['tipo_gasto']); nct = c4.text_input("Contrato", value=r['contrato'])
                c5,c6,c7 = st.columns(3)
                nm = c5.text_input("Monto", value=str(r['monto']).replace('.', ',')); nmo = c6.selectbox("Moneda", ["ARS", "USD"], index=["ARS", "USD"].index(r['moneda']))
                ncu = c7.text_input("Cuota", value=str(r['cuota']))
                c8,c9,c10 = st.columns(3)
                npg = c8.selectbox("Pago", OPCIONES_PAGO, index=OPCIONES_PAGO.index(r['forma_pago']) if r['forma_pago'] in OPCIONES_PAGO else 0)
                try: fd = pd.to_datetime(r['fecha_pago']).date()
                except: fd = datetime.date.today()
                nf = c9.date_input("Fecha", value=fd); npa = c10.checkbox("PAGADO", value=bool(r['pagado']))
                if st.form_submit_button("💾 Guardar"):
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("UPDATE movimientos SET tipo=%s, grupo=%s, tipo_gasto=%s, contrato=%s, monto=%s, moneda=%s, cuota=%s, forma_pago=%s, fecha_pago=%s, pagado=%s WHERE id=%s", (nt, ng, nc, nct, procesar_monto_input(nm), nmo, ncu, npg, str(nf), npa, idm))
                        conn.commit()
                    actualizar_saldos(mes_global); st.success("Ok"); st.rerun()
                if st.form_submit_button("❌ Eliminar"):
                    st.session_state['confirmar_eliminar_id'] = idm

            # Confirmacion fuera del form
            if st.session_state.get('confirmar_eliminar_id') == idm:
                st.warning(f"¿Seguro que queres eliminar **{r['tipo_gasto']}**?")
                ce1, ce2 = st.columns(2)
                if ce1.button("Si, eliminar", key="conf_del_si"):
                    with db_connection() as conn:
                        c = conn.cursor(); c.execute("DELETE FROM movimientos WHERE id=%s", (idm,)); conn.commit()
                    st.session_state.pop('confirmar_eliminar_id', None)
                    actualizar_saldos(mes_global); st.rerun()
                if ce2.button("Cancelar", key="conf_del_no"):
                    st.session_state.pop('confirmar_eliminar_id', None); st.rerun()

        elif len(selected) > 1:
            st.warning(f"Seleccionaste {len(selected)} movimientos.")
            if st.button("🗑️ Eliminar seleccionados"):
                st.session_state['confirmar_eliminar_multi'] = True
            if st.session_state.get('confirmar_eliminar_multi'):
                st.error(f"¿Seguro que queres eliminar **{len(selected)}** movimientos?")
                cm1, cm2 = st.columns(2)
                if cm1.button("Si, eliminar todos", key="conf_multi_si"):
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM movimientos WHERE id IN %s", (tuple([int(x['id']) for x in selected]),))
                        conn.commit()
                    st.session_state.pop('confirmar_eliminar_multi', None)
                    actualizar_saldos(mes_global); st.rerun()
                if cm2.button("Cancelar", key="conf_multi_no"):
                    st.session_state.pop('confirmar_eliminar_multi', None); st.rerun()
