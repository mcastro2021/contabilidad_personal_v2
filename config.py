import datetime

# --- COLORES GLOBALES ---
COLOR_MAP = {
    "GANANCIA": "#28a745",
    "GASTO": "#dc3545"
}

# --- GENERADOR DE MESES ---
MESES_NOMBRES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def generar_lista_meses(start_year=2026, end_year=2035):
    return [f"{m} {a}" for a in range(start_year, end_year + 1) for m in MESES_NOMBRES]

LISTA_MESES_LARGA = generar_lista_meses()

def obtener_indice_mes_actual():
    hoy = datetime.date.today()
    nombre_mes_actual = f"{MESES_NOMBRES[hoy.month - 1]} {hoy.year}"
    if nombre_mes_actual in LISTA_MESES_LARGA: return LISTA_MESES_LARGA.index(nombre_mes_actual)
    return 0

INDICE_MES_ACTUAL = obtener_indice_mes_actual()
OPCIONES_PAGO = ["Bancario", "Efectivo", "Transferencia", "Tarjeta de Debito", "Tarjeta de Credito"]
SMVM_BASE_2026 = {"Enero 2026": 341000.0, "Febrero 2026": 346800.0, "Marzo 2026": 352400.0, "Abril 2026": 357800.0, "Mayo 2026": 363000.0, "Junio 2026": 367800.0, "Julio 2026": 372400.0, "Agosto 2026": 376600.0}

LOTTIE_FINANCE = "https://lottie.host/02a55953-2736-4763-b183-116515b81045/L1O1fW89yB.json"
