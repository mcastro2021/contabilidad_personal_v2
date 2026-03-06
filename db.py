import os
import psycopg2
import psycopg2.pool
import datetime
import logging
from contextlib import contextmanager
from dotenv import load_dotenv
from auth import make_hashes

load_dotenv()
logger = logging.getLogger(__name__)

# --- POOL DE CONEXIONES ---
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        try:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=5,
                dsn=os.environ.get('DATABASE_URL')
            )
        except Exception as e:
            logger.critical(f"Pool Error: {e}")
            _pool = None
    return _pool

def get_db_connection():
    pool = _get_pool()
    if pool:
        try:
            return pool.getconn()
        except Exception as e:
            logger.error(f"Pool getconn error: {e}")
    # Fallback directo
    try: return psycopg2.connect(os.environ.get('DATABASE_URL'))
    except Exception as e:
        import streamlit as st
        logger.critical(f"DB Error: {e}"); st.error("Error BD"); st.stop()

def _put_connection(conn):
    pool = _get_pool()
    if pool:
        try: pool.putconn(conn); return
        except: pass
    try: conn.close()
    except: pass

@contextmanager
def db_connection():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        _put_connection(conn)

def init_db():
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS movimientos (id SERIAL PRIMARY KEY, fecha TEXT, mes TEXT, tipo TEXT, grupo TEXT, tipo_gasto TEXT, cuota TEXT, monto REAL, moneda TEXT, forma_pago TEXT, fecha_pago TEXT)''')
            for col in ["pagado BOOLEAN DEFAULT FALSE", "contrato TEXT DEFAULT ''"]:
                try: c.execute(f"ALTER TABLE movimientos ADD COLUMN {col}"); conn.commit()
                except: conn.rollback()
            c.execute('''CREATE TABLE IF NOT EXISTS grupos (nombre TEXT PRIMARY KEY)''')
            c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS deudas (id SERIAL PRIMARY KEY, nombre_deuda TEXT, monto_total REAL, moneda TEXT, fecha_inicio TEXT, estado TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS inversiones (id SERIAL PRIMARY KEY, tipo TEXT, entidad TEXT, monto_inicial REAL, tna REAL, fecha_inicio TEXT, plazo_dias INTEGER, estado TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS presupuestos (id SERIAL PRIMARY KEY, grupo TEXT UNIQUE, limite REAL, moneda TEXT DEFAULT 'ARS')''')
            c.execute('''CREATE TABLE IF NOT EXISTS recurrentes (id SERIAL PRIMARY KEY, tipo TEXT, grupo TEXT, tipo_gasto TEXT, contrato TEXT DEFAULT '', monto REAL, moneda TEXT, forma_pago TEXT, activo BOOLEAN DEFAULT TRUE)''')
            c.execute("SELECT count(*) FROM grupos")
            if c.fetchone()[0] == 0: c.executemany("INSERT INTO grupos VALUES (%s) ON CONFLICT DO NOTHING", [("AHORRO MANUEL",), ("CASA",), ("AUTO",), ("VARIOS",), ("DEUDAS",)])
            c.execute("SELECT count(*) FROM users")
            if c.fetchone()[0] == 0: c.execute("INSERT INTO users VALUES (%s, %s) ON CONFLICT DO NOTHING", ("admin", make_hashes("admin123")))
            conn.commit()
    except Exception as e: logger.critical(f"Init DB Error: {e}")

def generar_backup_sql():
    try:
        with db_connection() as conn:
            c = conn.cursor()
            tablas = ['grupos', 'users', 'deudas', 'movimientos', 'inversiones', 'presupuestos', 'recurrentes']
            script = "-- BACKUP V5 --\nTRUNCATE TABLE movimientos, deudas, grupos, users, inversiones RESTART IDENTITY CASCADE;\n\n"
            for t in tablas:
                try:
                    c.execute(f"SELECT * FROM {t}"); rows = c.fetchall()
                except:
                    conn.rollback(); continue
                if rows:
                    cols = [d[0] for d in c.description]
                    for r in rows:
                        vals = [f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if isinstance(v, str) else ("TRUE" if v is True else "FALSE" if v is False else ("NULL" if v is None else str(v))) for v in r]
                        script += f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(vals)}) ON CONFLICT DO NOTHING;\n"
            script += "\nSELECT setval('movimientos_id_seq', (SELECT MAX(id) FROM movimientos));\nSELECT setval('deudas_id_seq', (SELECT MAX(id) FROM deudas));\nSELECT setval('inversiones_id_seq', (SELECT MAX(id) FROM inversiones));\n"
            return script
    except: return "-- Error backup"
