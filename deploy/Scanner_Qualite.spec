# -*- mode: python ; coding: utf-8 -*-
#
# [BUILD] Executable du Scanner Qualite.
#
# hiddenimports est CRITIQUE : les dependances Azure, SQLAlchemy et OCR sont
# importees paresseusement dans le code (import local dans une fonction) pour
# que l application demarre meme si l une manque. PyInstaller ne les voit donc
# pas par analyse statique. Avec hiddenimports vide, elles etaient absentes de
# l executable livre et l ImportError etait avale silencieusement : c est la
# raison pour laquelle Key Vault et l OCR n ont jamais fonctionne en production.
#
# Apres chaque build, LIRE build/Scanner_Qualite/warn-Scanner_Qualite.txt et
# verifier qu aucun module de la liste ci-dessous n y figure comme manquant.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
for paquet in ("azure.identity", "azure.keyvault.secrets", "sqlalchemy.dialects.postgresql"):
    hiddenimports += collect_submodules(paquet)
hiddenimports += [
    "psycopg2",
    "pytesseract",
    "pdf2image",
    "pypdf",
    "openpyxl",
    "pandas",
    "src.azure_auth",
    "src.preflight",
    "src.dwh_repository",
    "src.ocr_engine",
    "src.code_resolver",
]

a = Analysis(
    ['..\\src\\scanner_app.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'matplotlib', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'IPython', 'jupyter', 'boto3', 'botocore', 'altair', 'bokeh',
              'plotly', 'tensorboard', 'tensorflow', 'torch', 'xgboost'],
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
    name='Scanner_Qualite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX fige le build sur un binaire de cette taille : desactive.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)