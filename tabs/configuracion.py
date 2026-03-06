import streamlit as st
import pandas as pd
import datetime
import io
from config import LISTA_MESES_LARGA, OPCIONES_PAGO
from db import db_connection, generar_backup_sql
from auth import make_hashes, check_hashes
from utils import formato_moneda_visual, procesar_monto_input


def render(grupos_db):
    st.header("⚙️ Configuración")

    # --- ADMINISTRAR GRUPOS ---
    st.subheader("📂 Administrar Grupos")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("nuevo_grupo_form"):
            ng = st.text_input("Nuevo Grupo").upper()
            if st.form_submit_button("Crear") and ng:
                with db_connection() as conn:
                    c=conn.cursor();c.execute("INSERT INTO grupos (nombre) VALUES (%s) ON CONFLICT DO NOTHING",(ng,));conn.commit()
                st.success(f"Creado {ng}");st.rerun()
    with c2:
        with st.form("borrar_grupo_form"):
            gb = st.selectbox("Borrar Grupo", grupos_db)
            if st.form_submit_button("Eliminar"):
                with db_connection() as conn:
                    c=conn.cursor();c.execute("DELETE FROM grupos WHERE nombre=%s",(gb,));conn.commit()
                st.warning(f"Eliminado {gb}");st.rerun()

    st.divider()

    # --- PRESUPUESTOS POR GRUPO ---
    with st.expander("📊 Presupuestos por Grupo", expanded=False):
        with db_connection() as conn:
            try:
                df_pres = pd.read_sql("SELECT * FROM presupuestos ORDER BY grupo", conn)
            except:
                df_pres = pd.DataFrame()
        if not df_pres.empty:
            st.dataframe(
                df_pres[['grupo', 'limite']].rename(columns={'grupo': 'Grupo', 'limite': 'Limite ($)'}),
                hide_index=True, use_container_width=True
            )

        with st.form("presupuesto_form"):
            cp1, cp2 = st.columns(2)
            pg = cp1.selectbox("Grupo", grupos_db, key="pres_grupo")
            pl = cp2.text_input("Limite mensual ($)", "0,00", key="pres_limite")
            if st.form_submit_button("Guardar Presupuesto"):
                with db_connection() as conn:
                    c = conn.cursor()
                    c.execute("INSERT INTO presupuestos (grupo, limite) VALUES (%s, %s) ON CONFLICT (grupo) DO UPDATE SET limite=%s",
                              (pg, procesar_monto_input(pl), procesar_monto_input(pl)))
                    conn.commit()
                st.success(f"Presupuesto de {pg} actualizado"); st.rerun()

        if not df_pres.empty:
            with st.form("borrar_pres_form"):
                pb = st.selectbox("Eliminar presupuesto de", df_pres['grupo'].tolist())
                if st.form_submit_button("Eliminar Presupuesto"):
                    with db_connection() as conn:
                        c = conn.cursor(); c.execute("DELETE FROM presupuestos WHERE grupo=%s", (pb,)); conn.commit()
                    st.success("Eliminado"); st.rerun()

    # --- GASTOS RECURRENTES ---
    with st.expander("🔄 Gastos Recurrentes", expanded=False):
        with db_connection() as conn:
            try:
                df_rec = pd.read_sql("SELECT * FROM recurrentes WHERE activo=TRUE ORDER BY grupo, tipo_gasto", conn)
            except:
                df_rec = pd.DataFrame()

        if not df_rec.empty:
            st.caption("Gastos que se generan automaticamente cada mes")
            df_show_rec = df_rec[['tipo_gasto', 'grupo', 'monto', 'moneda', 'forma_pago']].copy()
            df_show_rec['monto'] = df_rec.apply(lambda x: formato_moneda_visual(x['monto'], x['moneda']), axis=1)
            st.dataframe(df_show_rec.rename(columns={
                'tipo_gasto': 'Concepto', 'grupo': 'Grupo', 'monto': 'Monto',
                'moneda': 'Moneda', 'forma_pago': 'Forma Pago'
            }), hide_index=True, use_container_width=True)

        with st.form("nuevo_recurrente"):
            st.subheader("Agregar Gasto Recurrente")
            cr1, cr2 = st.columns(2)
            rec_tipo = cr1.selectbox("Tipo", ["GASTO", "GANANCIA"], key="rec_tipo")
            rec_grupo = cr2.selectbox("Grupo", grupos_db, key="rec_grupo")
            cr3, cr4 = st.columns(2)
            rec_concepto = cr3.text_input("Concepto", key="rec_concepto")
            rec_contrato = cr4.text_input("Cuenta o Contrato", key="rec_contrato")
            cr5, cr6, cr7 = st.columns(3)
            rec_monto = cr5.text_input("Monto", "0,00", key="rec_monto")
            rec_moneda = cr6.selectbox("Moneda", ["ARS", "USD"], key="rec_moneda")
            rec_pago = cr7.selectbox("Forma de Pago", OPCIONES_PAGO, key="rec_pago")
            if st.form_submit_button("Agregar Recurrente"):
                with db_connection() as conn:
                    c = conn.cursor()
                    c.execute("INSERT INTO recurrentes (tipo, grupo, tipo_gasto, contrato, monto, moneda, forma_pago) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                              (rec_tipo, rec_grupo, rec_concepto, rec_contrato, procesar_monto_input(rec_monto), rec_moneda, rec_pago))
                    conn.commit()
                st.success("Recurrente agregado"); st.rerun()

        if not df_rec.empty:
            with st.form("borrar_rec_form"):
                rec_del = st.selectbox("Desactivar recurrente", df_rec['tipo_gasto'].tolist(), key="rec_del")
                if st.form_submit_button("Desactivar"):
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("UPDATE recurrentes SET activo=FALSE WHERE tipo_gasto=%s AND activo=TRUE", (rec_del,))
                        conn.commit()
                    st.success("Desactivado"); st.rerun()

        st.caption("Usa 'Generar Recurrentes' para crear los movimientos del mes actual")
        mes_rec = st.selectbox("Mes destino", LISTA_MESES_LARGA, key="mes_recurrentes")
        if st.button("Generar Recurrentes en Mes"):
            with db_connection() as conn:
                try:
                    df_rec_activos = pd.read_sql("SELECT * FROM recurrentes WHERE activo=TRUE", conn)
                except:
                    df_rec_activos = pd.DataFrame()
                if df_rec_activos.empty:
                    st.warning("No hay recurrentes activos")
                else:
                    c = conn.cursor()
                    count = 0
                    for _, r in df_rec_activos.iterrows():
                        c.execute("SELECT id FROM movimientos WHERE mes=%s AND tipo_gasto=%s AND grupo=%s", (mes_rec, r['tipo_gasto'], r['grupo']))
                        if not c.fetchone():
                            c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,contrato,cuota,monto,moneda,forma_pago,fecha_pago,pagado) VALUES (%s,%s,%s,%s,%s,%s,'1/1',%s,%s,%s,%s,FALSE)",
                                      (str(datetime.date.today()), mes_rec, r['tipo'], r['grupo'], r['tipo_gasto'], r['contrato'], float(r['monto']), r['moneda'], r['forma_pago'], str(datetime.date.today())))
                            count += 1
                    conn.commit()
                    st.success(f"{count} movimientos recurrentes generados en {mes_rec}")

    st.divider()

    # --- REPLICADOR ---
    with st.expander("🔄 REPLICADOR DE GASTOS", expanded=False):
        c1, c2 = st.columns(2); mm = c1.selectbox("Mes Modelo", LISTA_MESES_LARGA)
        with db_connection() as conn:
            dfm=pd.read_sql("SELECT * FROM movimientos WHERE mes=%s AND tipo='GASTO'", conn, params=(mm,))
        if not dfm.empty:
            gs = st.multiselect("Gastos a copiar", dfm['tipo_gasto'].unique()); md = st.multiselect("Destino", LISTA_MESES_LARGA)
            if st.button("Replicar"):
                with db_connection() as conn:
                    c=conn.cursor()
                    for m in md:
                        for g in gs:
                            r=dfm[dfm['tipo_gasto']==g].iloc[0]
                            c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,contrato,cuota,monto,moneda,forma_pago,fecha_pago,pagado) VALUES (%s,%s,%s,%s,%s,%s,'1/1',%s,%s,%s,%s,FALSE)", (str(datetime.date.today()),m,r['tipo'],r['grupo'],r['tipo_gasto'],r['contrato'],float(r['monto']),r['moneda'],r['forma_pago'],str(datetime.date.today())))
                    conn.commit()
                st.success("Replicado")

    # --- BACKUP Y CLONACION ---
    bc1, bc2 = st.columns(2)
    bc1.download_button("📦 BACKUP SQL", generar_backup_sql(), "backup.sql")

    # Export Excel
    with db_connection() as conn:
        df_excel = pd.read_sql("SELECT * FROM movimientos ORDER BY mes, tipo, grupo", conn)
    if not df_excel.empty:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_excel.to_excel(writer, sheet_name='Todos', index=False)
            for mes in df_excel['mes'].unique():
                sheet_name = mes[:31]  # Excel max 31 chars
                df_excel[df_excel['mes'] == mes].to_excel(writer, sheet_name=sheet_name, index=False)
        bc2.download_button("📊 EXPORTAR EXCEL", output.getvalue(), "contabilidad.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    c1,c2,c3 = st.columns(3); ms=c1.selectbox("Desde", LISTA_MESES_LARGA); md_clone=c2.selectbox("Hasta", ["TODO"]+LISTA_MESES_LARGA)
    if c3.button("Clonar Mes"):
        with db_connection() as conn:
            c=conn.cursor()
            df=pd.read_sql("SELECT * FROM movimientos WHERE mes=%s", conn, params=(ms,))
            tgs=[m for m in LISTA_MESES_LARGA if m.split(' ')[1]==ms.split(' ')[1]] if md_clone=="TODO" else [md_clone]
            for t in tgs:
                if t==ms: continue
                c.execute("DELETE FROM movimientos WHERE mes=%s",(t,))
                for i,r in df.iterrows(): c.execute("INSERT INTO movimientos (fecha,mes,tipo,grupo,tipo_gasto,contrato,cuota,monto,moneda,forma_pago,fecha_pago) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(datetime.date.today()),t,r['tipo'],r['grupo'],r['tipo_gasto'],r['contrato'],r['cuota'],float(r['monto']),r['moneda'],r['forma_pago'],r['fecha_pago']))
            conn.commit()
        st.success("Hecho");st.rerun()

    st.divider()
    st.subheader("🔑 Cambiar Contraseña")
    with st.form("cambiar_password"):
        cp1, cp2, cp3 = st.columns(3)
        pass_actual = cp1.text_input("Contraseña actual", type="password")
        pass_nueva = cp2.text_input("Nueva contraseña", type="password")
        pass_conf = cp3.text_input("Confirmar nueva", type="password")
        if st.form_submit_button("Actualizar Contraseña"):
            if not pass_actual or not pass_nueva or not pass_conf:
                st.error("Completá todos los campos.")
            elif pass_nueva != pass_conf:
                st.error("La nueva contraseña y la confirmación no coinciden.")
            elif len(pass_nueva) < 6:
                st.error("La nueva contraseña debe tener al menos 6 caracteres.")
            else:
                with db_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT password FROM users WHERE username=%s", (st.session_state['username'],))
                    row = c.fetchone()
                    if row and check_hashes(pass_actual, row[0]):
                        c.execute("UPDATE users SET password=%s WHERE username=%s", (make_hashes(pass_nueva), st.session_state['username']))
                        conn.commit(); st.success("Contraseña actualizada correctamente.")
                    else:
                        st.error("La contraseña actual es incorrecta.")
