# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None
backend_dir = os.path.abspath(SPECPATH)
workspace_dir = os.path.dirname(backend_dir)
frontend_dist = os.path.join(workspace_dir, 'frontend', 'dist')

datas = [
    (os.path.join(backend_dir, 'app'), 'app'),
]

# Include compiled React frontend dist if built
if os.path.exists(frontend_dist) and os.path.exists(os.path.join(frontend_dist, 'index.html')):
    datas.append((frontend_dist, 'dist'))

hidden_imports = [
    # Desktop webview
    'webview',
    'webview.platforms',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'clr',
    'clr_loader',
    'pythonnet',
    'proxy_tools',
    'bottle',

    # Uvicorn / ASGI
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',

    # FastAPI / Starlette
    'fastapi',
    'fastapi.staticfiles',
    'fastapi.middleware.cors',
    'starlette',
    'starlette.staticfiles',
    'starlette.middleware.cors',

    # Pydantic
    'pydantic',
    'pydantic_settings',

    # Computer vision & processing
    'cv2',
    'numpy',
    'PIL',
    'PIL.Image',

    # Firebase & Supabase
    'firebase_admin',
    'firebase_admin.credentials',
    'firebase_admin.db',
    'firebase_admin.messaging',
    'supabase',
    'gotrue',
    'postgrest',
    'storage3',
    'realtime',

    # Standard / utility
    'sqlite3',
    'email.mime.text',
    'email.mime.multipart',
    'smtplib',
    'dotenv',
    'ctypes',
    'ctypes.wintypes',
    'urllib.request',
    'urllib.error'
]

a = Analysis(
    [os.path.join(backend_dir, 'desktop_launcher.py')],
    pathex=[backend_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TRINETRA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Windowed desktop launcher with ZERO CMD console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(backend_dir, 'app', 'assets', 'trinetra.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TRINETRA',
)
