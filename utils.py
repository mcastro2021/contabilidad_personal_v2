import os
import datetime
import requests
import pandas as pd
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def load_lottieurl(url):
    try: return requests.get(url, timeout=3).json()
    except: return None

def formato_moneda_visual(valor, moneda):
    if valor is None or pd.isna(valor): return ""
    try: return f"{'US$ ' if moneda == 'USD' else '$ '}{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(valor)

def procesar_monto_input(t):
    if not t: return 0.0
    try: return float(str(t).strip().replace("$","").replace("US","").replace(" ","").replace(".","").replace(",", ".")) if not isinstance(t, (int, float)) else float(t)
    except: return 0.0

def enviar_notificacion(asunto, mensaje):
    try:
        sender_email = os.environ.get("EMAIL_SENDER")
        sender_password = os.environ.get("EMAIL_PASSWORD")
        receiver_email = os.environ.get("EMAIL_RECEIVER")

        if not all([sender_email, sender_password, receiver_email]): return

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = f"🔔 FINANZAS V5: {asunto}"
        msg.attach(MIMEText(mensaje, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        logger.info(f"Email enviado: {asunto}")
    except Exception as e:
        logger.error(f"Fallo envío email: {e}")

def generar_alertas(df, dolar_val):
    hoy = datetime.date.today()
    limite = hoy + datetime.timedelta(days=5)
    mensajes = []
    total_vencido = 0.0
    total_por_vencer = 0.0
    total_por_cobrar = 0.0

    if df.empty: return mensajes, 0, 0, 0

    pendientes = df[(df['tipo'] == 'GASTO') & (df['pagado'] == False)].copy()
    for i, r in pendientes.iterrows():
        try:
            f_pago = pd.to_datetime(r['fecha_pago']).date()
            monto_real = float(r['monto']) * dolar_val if r['moneda'] == 'USD' else float(r['monto'])
            if f_pago < hoy:
                mensajes.append(f"🚨 **VENCIDO:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])}) - {f_pago.strftime('%d/%m')}")
                total_vencido += monto_real
            elif hoy <= f_pago <= limite:
                dias = (f_pago - hoy).days
                txt = "HOY" if dias == 0 else f"en {dias} días"
                mensajes.append(f"⚠️ **Vence {txt}:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])})")
                total_por_vencer += monto_real
        except: pass

    ingresos = df[(df['tipo'] == 'GANANCIA') & (df['pagado'] == False) & (df['tipo_gasto'] != 'Ahorro Mes Anterior')].copy()
    for i, r in ingresos.iterrows():
        try:
            f_cobro = pd.to_datetime(r['fecha_pago']).date()
            monto_real = float(r['monto']) * dolar_val if r['moneda'] == 'USD' else float(r['monto'])
            if f_cobro < hoy:
                mensajes.append(f"⏳ **Cobro Atrasado:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])}) - Era el {f_cobro.strftime('%d/%m')}")
                total_por_cobrar += monto_real
            elif hoy <= f_cobro <= limite:
                dias = (f_cobro - hoy).days
                txt = "HOY" if dias == 0 else f"en {dias} días"
                mensajes.append(f"💵 **Cobras {txt}:** {r['tipo_gasto']} ({formato_moneda_visual(r['monto'], r['moneda'])})")
                total_por_cobrar += monto_real
        except: pass

    return mensajes, total_vencido, total_por_vencer, total_por_cobrar
