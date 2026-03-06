import datetime
import requests
import streamlit as st
from config import LISTA_MESES_LARGA, SMVM_BASE_2026
from db import db_connection

def calcular_monto_salario_mes(m):
    if m in SMVM_BASE_2026:
        val = SMVM_BASE_2026[m] * 2.5
        return val * 1.5 if "Junio" in m else val
    if "2026" in m:
        try:
            meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            nom = m.split(" ")[0]
            if nom in meses[8:]:
                ini, fin = SMVM_BASE_2026["Enero 2026"], SMVM_BASE_2026["Agosto 2026"]
                prom = (fin - ini) / 7; base = fin + (prom * (meses.index(nom) - 7))
                val = base * 2.5; return val * 1.5 if nom == "Diciembre" else val
        except: pass
    return None

def automatizaciones():
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, mes FROM movimientos WHERE tipo_gasto = 'SALARIO CHICOS'")
            for r in c.fetchall():
                v = calcular_monto_salario_mes(r[1])
                if v: c.execute("UPDATE movimientos SET monto=%s WHERE id=%s", (v, r[0]))
            for i, m in enumerate(LISTA_MESES_LARGA):
                c.execute("UPDATE movimientos SET monto=%s WHERE mes=%s AND tipo_gasto='TERRENO'", (13800.0 * ((1.04) ** i), m))
            conn.commit()
    except: pass

def actualizar_saldos(mes):
    try:
        with db_connection() as conn:
            c = conn.cursor(); idx = LISTA_MESES_LARGA.index(mes)
            for i in range(idx, min(len(LISTA_MESES_LARGA)-1, idx+24)):
                ma, ms = LISTA_MESES_LARGA[i], LISTA_MESES_LARGA[i+1]
                c.execute("SELECT COALESCE(SUM(CASE WHEN tipo='GANANCIA' THEN monto ELSE 0 END),0) - COALESCE(SUM(CASE WHEN tipo='GASTO' THEN monto ELSE 0 END),0) FROM movimientos WHERE mes=%s AND moneda='ARS'", (ma,))
                saldo = c.fetchone()[0] or 0.0
                c.execute("SELECT id FROM movimientos WHERE mes=%s AND tipo_gasto='Ahorro Mes Anterior'", (ms,))
                r = c.fetchone()
                if r: c.execute("UPDATE movimientos SET monto=%s, pagado=TRUE WHERE id=%s", (saldo, r[0]))
                else: c.execute("INSERT INTO movimientos (fecha, mes, tipo, grupo, tipo_gasto, cuota, monto, moneda, forma_pago, fecha_pago, pagado) VALUES (%s,%s,'GANANCIA','AHORRO MANUEL','Ahorro Mes Anterior','1/1',%s,'ARS','Automático',%s, TRUE)", (str(datetime.date.today()), ms, saldo, str(datetime.date.today())))
                conn.commit()
    except: pass

@st.cache_data(ttl=60)
def get_dolar():
    try: return (float(requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3).json()['compra']) + float(requests.get("https://dolarapi.com/v1/dolares/blue", timeout=3).json()['venta'])) / 2, "(Ref)"
    except: return 1480.0, "(Ref)"
