# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Manuel\\Documents\\Cursor\\contabilidad_personal_v2\\.venv\\Lib\\site-packages\\streamlit\\static', 'streamlit/static'), ('C:\\Users\\Manuel\\Documents\\Cursor\\contabilidad_personal_v2\\.venv\\Lib\\site-packages\\streamlit\\runtime', 'streamlit/runtime'), ('C:\\Users\\Manuel\\Documents\\Cursor\\contabilidad_personal_v2\\.venv\\Lib\\site-packages\\streamlit_lottie\\frontend', 'streamlit_lottie/frontend'), ('app.py', '.'), ('.env', '.')],
    hiddenimports=['email', 'email.mime.text', 'email.mime.multipart', 'email.mime.base', 'smtplib', 'pandas', 'plotly', 'psycopg2', 'sklearn', 'dotenv', 'streamlit_lottie', 'streamlit.web.server', 'streamlit.runtime.scriptrunner.magic_funcs'],
    hookspath=['./hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ContabilidadV3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
