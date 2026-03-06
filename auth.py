import hashlib
import streamlit as st
from utils import load_lottieurl
from streamlit_lottie import st_lottie
from config import LOTTIE_FINANCE

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

def make_hashes(p):
    if HAS_BCRYPT:
        return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    return hashlib.sha256(str.encode(p)).hexdigest()

def check_hashes(p, h):
    if HAS_BCRYPT and h.startswith('$2b$'):
        return bcrypt.checkpw(p.encode('utf-8'), h.encode('utf-8'))
    return hashlib.sha256(str.encode(p)).hexdigest() == h

def _upgrade_hash_if_needed(username, password):
    if not HAS_BCRYPT:
        return
    new_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    from db import db_connection
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET password=%s WHERE username=%s", (new_hash, username))
        conn.commit()

def login_screen():
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if 'username' not in st.session_state: st.session_state['username'] = ''

    if not st.session_state['logged_in']:
        st.markdown("<h1 style='text-align: center;'>🔐 ACCESO FINANZAS</h1>", unsafe_allow_html=True)
        lottie = load_lottieurl(LOTTIE_FINANCE)
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if lottie: st_lottie(lottie, height=150)
            with st.form("login"):
                u = st.text_input("Usuario"); p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Entrar", use_container_width=True):
                    from db import db_connection
                    with db_connection() as conn:
                        c = conn.cursor()
                        c.execute("SELECT password FROM users WHERE username=%s", (u,))
                        row = c.fetchone()
                        if row and check_hashes(p, row[0]):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = u
                            if not row[0].startswith('$2b$'):
                                _upgrade_hash_if_needed(u, p)
                            st.rerun()
                        else:
                            st.error("Usuario o contraseña incorrectos")
        st.stop()
