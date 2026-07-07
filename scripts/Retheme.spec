# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

# This spec lives in scripts\; the app source and entry point are one level up.
_proj = os.path.dirname(SPECPATH)
_static = os.path.join(_proj, 'pptx_template_tool', 'webapp', 'static')

datas = [(_static, 'pptx_template_tool\\webapp\\static')]
hiddenimports = ['multipart']
datas += collect_data_files('pptx')
hiddenimports += collect_submodules('uvicorn')


a = Analysis(
    [os.path.join(SPECPATH, 'portable_main.py')],
    pathex=[_proj],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
    [],
    exclude_binaries=True,
    name='Retheme',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Retheme',
)
