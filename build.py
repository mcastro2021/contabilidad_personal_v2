import PyInstaller.__main__
import os
import streamlit
import streamlit_lottie

# 1. Obtener la ruta de Streamlit
streamlit_folder = os.path.dirname(streamlit.__file__)
streamlit_static = os.path.join(streamlit_folder, "static")
streamlit_runtime = os.path.join(streamlit_folder, "runtime")

# 2. Obtener la ruta de Streamlit Lottie
lottie_folder = os.path.dirname(streamlit_lottie.__file__)
lottie_frontend = os.path.join(lottie_folder, "frontend")

print(f"📍 Streamlit en: {streamlit_folder}")
print(f"📍 Lottie en: {lottie_folder}")

# 3. Ejecutar PyInstaller
PyInstaller.__main__.run([
    'run_app.py',
    '--name=ContabilidadV3',
    '--onefile',
    '--clean',
    '--noconfirm',
    
    # --- COPIAR ARCHIVOS ---
    f'--add-data={streamlit_static};streamlit/static',
    f'--add-data={streamlit_runtime};streamlit/runtime',
    f'--add-data={lottie_frontend};streamlit_lottie/frontend',
    '--add-data=app.py;.',
    '--add-data=.env;.',
    
    # --- IMPORTACIONES OCULTAS (EMAIL FIX) ---
    '--hidden-import=email',
    '--hidden-import=email.mime.text',
    '--hidden-import=email.mime.multipart',
    '--hidden-import=email.mime.base',
    '--hidden-import=smtplib',
    
    # --- IMPORTACIONES OCULTAS (RESTO) ---
    '--hidden-import=pandas',
    '--hidden-import=plotly',
    '--hidden-import=psycopg2',
    '--hidden-import=sklearn',
    '--hidden-import=dotenv',
    '--hidden-import=streamlit_lottie',
    '--hidden-import=streamlit.web.server',
    '--hidden-import=streamlit.runtime.scriptrunner.magic_funcs',
    
    '--additional-hooks-dir=./hooks',
])

print("✅ COMPILACIÓN FINALIZADA CORRECTAMENTE")