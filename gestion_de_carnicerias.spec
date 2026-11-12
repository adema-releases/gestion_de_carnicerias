# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules


block_cipher = None
PROJECT_ROOT = os.path.abspath(SPECPATH)
APP_NAME = "GestionDeCarnicerias"
ICON_FILE = os.path.join(PROJECT_ROOT, "static", "img", "ico.ico")

datas = []
binaries = []
hiddenimports = []

DIRS_TO_INCLUDE = [
    "templates",
    "static",
    "staticfiles",
    "locale",
    os.path.join("pos", "templates"),
    os.path.join("tesoreria", "templates"),
    os.path.join("dashboard", "templates"),
    os.path.join("central", "templates"),
    # Fotos ilustrativas del catálogo que asigna seed_catan
    os.path.join("inventario", "fotos_catalogo"),
    # Guía rápida: plantillas, índices generados desde documentacion/ y el JS/CSS del panel
    os.path.join("ayuda", "templates"),
    os.path.join("ayuda", "data"),
    os.path.join("ayuda", "assets"),
]

# Las plantillas de cada app se buscan solas: una carpeta <app>/templates nueva
# no puede quedar afuera del instalador (en 0.0.9/0.1.0 faltó inventario/templates
# y Productos y la lista de precios daban error 500).
for app_dir in sorted(os.listdir(PROJECT_ROOT)):
    plantillas = os.path.join(app_dir, "templates")
    if (app_dir not in ("venv", "dist", "build", "staticfiles")
            and os.path.isdir(os.path.join(PROJECT_ROOT, plantillas))
            and plantillas not in DIRS_TO_INCLUDE):
        DIRS_TO_INCLUDE.append(plantillas)

for directory in DIRS_TO_INCLUDE:
    source = os.path.join(PROJECT_ROOT, directory)
    if os.path.exists(source):
        datas.append((source, directory))

APP_MODULES = [
    "gestion_de_carnicerias",
    "core",
    "tesoreria",
    "inventario",
    "compras",
    "ventas",
    "gastos",
    "pos",
    "dashboard",
    "recepcion",
    "central",
    "agente",
    "ayuda",
]

for module in APP_MODULES:
    hiddenimports += collect_submodules(module)

# collect_submodules descarta en silencio los módulos que no puede importar sin
# Django configurado (los comandos que importan modelos, como seed_catan). Los
# comandos de manage.py se suman leyendo las carpetas.
for module in APP_MODULES:
    commands_dir = os.path.join(PROJECT_ROOT, module, "management", "commands")
    if os.path.isdir(commands_dir):
        for filename in os.listdir(commands_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                hiddenimports.append(f"{module}.management.commands.{filename[:-3]}")

MANUAL_HIDDEN_IMPORTS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.core.management",
    "django.core.management.commands.migrate",
    "django.core.management.commands.runserver",
    "core.management.commands.init_system",
    "dotenv",
    "import_export",
    "jazzmin",
    "openpyxl",
    "PIL",
    "psutil",
    "psycopg2",
    "pystray",
    # pywin32 lo importa recién al leer fechas de Windows (EnumJobs / GetPrinter en la prueba
    # de impresora); PyInstaller no lo ve y el ejecutable fallaba con "No module named 'win32timezone'".
    "win32timezone",
    "reportlab",
    "requests",
]
# Los binarios de PostgreSQL (vendor\pgsql) no van en el bundle: los copia el
# instalador a <instalación>\pgsql, donde los busca run_server.py.

hiddenimports += MANUAL_HIDDEN_IMPORTS

for library in ["django", "jazzmin", "import_export", "openpyxl", "reportlab"]:
    library_datas, library_binaries, library_hiddenimports = collect_all(library)
    datas += library_datas
    binaries += library_binaries
    hiddenimports += library_hiddenimports

a = Analysis(
    ["run_server.py"],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)