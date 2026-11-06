# Django a Windows Desktop App: Guia probada de empaquetado

Este documento describe el patron probado para convertir una app Django en una aplicacion Windows instalable: `.exe` local, instalador NSIS, icono en la bandeja del sistema, acceso por navegador local, base de datos persistente fuera de `Program Files`, logs persistentes y upgrades que aplican migraciones sin pisar datos del cliente.

La regla principal es separar siempre estos dos mundos:

```text
C:\Program Files\<App>\   ejecutable y recursos de solo lectura
C:\<app>\                 datos persistentes: DB, logs, media, version instalada
```

En Gestion de Carnicerias usamos:

```text
C:\GestionDeCarnicerias\pgdata\                     cluster de PostgreSQL de la app
C:\GestionDeCarnicerias\db\clave_postgres.txt       clave generada del usuario de la base
C:\GestionDeCarnicerias\config.env                  configuracion de la PC (sincronizacion, base externa)
C:\GestionDeCarnicerias\logs\gestion_de_carnicerias.log
C:\GestionDeCarnicerias\logs\postgres.log
C:\GestionDeCarnicerias\media\
```

> **Actualizado 2026-11-03: la base es PostgreSQL, no SQLite.** El instalador trae los binarios de
> PostgreSQL 18 en `<instalacion>\pgsql`. `run_server.py` y `postgres_local.py` crean el cluster
> la primera vez (`127.0.0.1:5433`, usuario `carnicerias`), lo arrancan al abrir la app y lo
> apagan al salir. Si `config.env` define `DB_HOST`, se usa ese servidor en lugar del propio.
> Los ejemplos de abajo que mencionan `db.sqlite3` son del patron original; el codigo real es
> el de `run_server.py`.

---

## Componentes

| Archivo | Rol |
|---|---|
| `version.py` | Fuente unica de version |
| `up_version.py` | Actualiza version en `version.py` y `installer.nsi` |
| `run_server.py` | Entry point del ejecutable empaquetado |
| `<app>.spec` | Configuracion de PyInstaller |
| `installer.nsi` | Script del instalador NSIS |
| `requirements_win.txt` | Dependencias de empaquetado Windows |
| `build_release.bat` | Orquestador del build completo |

---

## Flujo de build

```text
Codigo Django
     |
     v
build_release.bat
     |
     +-- pip install -r requirements_win.txt
     +-- python manage.py collectstatic --noinput --clear
     +-- python -m PyInstaller <app>.spec --clean --noconfirm
     +-- makensis installer.nsi
     +-- genera SHA256
     +-- copia artefactos a exe\<version>\
```

Resultado esperado:

```text
dist\<App>\<App>.exe
<App>_Installer_v<X.Y.Z>.exe
<App>_Installer_v<X.Y.Z>.exe.sha256
exe\<X.Y.Z>\<App>_Installer_v<X.Y.Z>.exe
exe\<X.Y.Z>\<App>_Installer_v<X.Y.Z>.exe.sha256
```

---

## Flujo en produccion

Cuando el usuario instala y ejecuta la app:

```text
Usuario abre <App>.exe
     |
     v
run_server.py
     |
     +-- crea carpetas persistentes en C:\<app>\
     +-- configura stdout/stderr hacia el log si no hay consola
     +-- configura variables de entorno para Django
     +-- inicializa django.setup() antes de usar call_command()
     +-- evita doble instancia con lock file
     +-- si no existe DB: corre comando inicial de setup
     +-- si existe DB y cambio la version: corre migrate --noinput
     +-- si la version ya estaba aplicada: no toca la DB
     +-- levanta runserver local sin autoreload
     +-- abre http://127.0.0.1:<PORT>/...
     +-- mantiene vivo el proceso con icono en bandeja
```

---

## 1. `version.py`

`version.py` es la unica fuente de version.

```python
__version__ = "1.0.0"


def get_version():
    return __version__
```

No escribas la version manualmente en varios lugares. El script de versionado debe sincronizar el instalador.

---

## 2. `up_version.py`

Uso:

```powershell
python .\up_version.py 1.0.1
```

Debe validar formato `X.Y.Z` y actualizar:

```text
version.py       __version__ = "X.Y.Z"
installer.nsi    !define APP_VERSION "X.Y.Z"
installer.nsi    !define APP_BUILD "X.Y.Z.0"
```

`APP_BUILD` tiene 4 segmentos porque Windows lo requiere para metadata de version.

---

## 3. `run_server.py`

`run_server.py` es el entry point real del ejecutable. No empaquetes `manage.py` como app final.

### Constantes a adaptar

```python
APP_NAME = "GestionDeCarnicerias"
PROJECT_NAME = "gestion_de_carnicerias"
PORT = 8250
LOCAL_URL = f"http://127.0.0.1:{PORT}/pos/"

DATA_ROOT = Path(r"C:\GestionDeCarnicerias")
DB_DIR = DATA_ROOT / "db"
LOG_DIR = DATA_ROOT / "logs"
MEDIA_DIR = DATA_ROOT / "media"
DB_PATH = DB_DIR / "db.sqlite3"
LOG_PATH = LOG_DIR / "gestion_de_carnicerias.log"
LOCK_PATH = DATA_ROOT / "gestion_de_carnicerias.lock"
INSTALLED_VERSION_PATH = DATA_ROOT / "installed_version.txt"
```

Para otra app, cambia `APP_NAME`, `PROJECT_NAME`, `PORT`, `LOCAL_URL`, nombres de carpetas y nombre de log.

### Carpetas persistentes

```python
def ensure_runtime_dirs():
    for path in (DATA_ROOT, DB_DIR, LOG_DIR, MEDIA_DIR):
        path.mkdir(parents=True, exist_ok=True)
```

Nunca escribas DB, media, logs ni `.env` dentro de `Program Files`.

### Streams seguros en modo windowed

Con PyInstaller `console=False`, Windows puede dejar `sys.stdout` y `sys.stderr` como `None`. Django escribe en `stdout` durante `runserver`, `migrate` y checks internos. Si no se corrige, aparece:

```text
AttributeError: 'NoneType' object has no attribute 'write'
```

Solucion obligatoria:

```python
_STDOUT_LOG_HANDLE = None


def configure_standard_streams():
    global _STDOUT_LOG_HANDLE
    ensure_runtime_dirs()
    if sys.stdout is None or sys.stderr is None or not hasattr(sys.stdout, "write") or not hasattr(sys.stderr, "write"):
        if _STDOUT_LOG_HANDLE is None:
            _STDOUT_LOG_HANDLE = LOG_PATH.open("a", encoding="utf-8", buffering=1)
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            sys.stdout = _STDOUT_LOG_HANDLE
        if sys.stderr is None or not hasattr(sys.stderr, "write"):
            sys.stderr = _STDOUT_LOG_HANDLE


def get_command_stream():
    configure_standard_streams()
    return sys.stdout or _STDOUT_LOG_HANDLE
```

Llama `configure_standard_streams()` desde `configure_logging()` y `configure_environment()`.

### Inicializar Django antes de `call_command()`

Si se usa `call_command()` sin inicializar Django, pueden aparecer errores como:

```text
django.core.exceptions.AppRegistryNotReady:
The translation infrastructure cannot be initialized before the apps registry is ready
```

Solucion obligatoria:

```python
import django
from django.apps import apps


def ensure_django_ready():
    configure_environment()
    if not apps.ready:
        django.setup()
```

Llama `ensure_django_ready()` antes de cualquier `call_command()`.

### Ejecutar comandos Django con streams explicitos

Evita `execute_from_command_line()` dentro del exe windowed. Usa `call_command()` con `stdout` y `stderr` explicitos.

```python
from django.core.management import call_command


def run_management_command(args, logger):
    logger.info("Ejecutando manage.py %s", " ".join(args))
    ensure_django_ready()
    command_stream = get_command_stream()
    command_args = [arg for arg in args[1:] if arg != "--noinput"]
    command_options = {"stdout": command_stream, "stderr": command_stream}
    if "--noinput" in args:
        command_options["interactive"] = False
    call_command(args[0], *command_args, **command_options)
```

Para `runserver`:

```python
def run_django_server(logger):
    configure_environment()
    try:
        ensure_django_ready()
        command_stream = get_command_stream()
        call_command(
            "runserver",
            f"127.0.0.1:{PORT}",
            use_reloader=False,
            insecure_serving=True,
            stdout=command_stream,
            stderr=command_stream,
        )
    except Exception:
        logger.exception("El servidor Django se detuvo por un error")
```

### Variables de entorno runtime

```python
def configure_environment():
    ensure_runtime_dirs()
    configure_standard_streams()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"{PROJECT_NAME}.settings")
    os.environ["GESTION_CARNICERIAS_DESKTOP"] = "1"
    os.environ["DB_NAME"] = str(DB_PATH)
    os.environ["MEDIA_ROOT"] = str(MEDIA_DIR)
    os.environ["LOG_DIR"] = str(LOG_DIR)
    os.environ.setdefault("SECRET_KEY", "django-insecure-local-runtime-key")
    os.environ.setdefault("DEBUG", "True")
    os.environ.setdefault("ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:8250,http://localhost:8250")
```

### Bootstrap de DB y upgrades

La DB se controla por si existe la tabla `django_migrations` (`postgres_local.base_migrada`) y por `installed_version.txt`. Antes de eso, `iniciar_base()` arranca el PostgreSQL propio y crea la base si falta.

```python
def bootstrap_database(logger):
    configure_environment()
    database_exists = is_database_present()
    installed_version = read_installed_version()

    if not database_exists:
        logger.info("No se detecto base de datos. Inicializando %s", __version__)
        run_management_command(["init_system"], logger)
        write_installed_version()
        return

    if installed_version != __version__:
        logger.info("Actualizando base existente desde %s a %s", installed_version or "desconocida", __version__)
        run_management_command(["migrate", "--noinput"], logger)
        write_installed_version()
        return

    logger.info("Base de datos ya actualizada para %s", __version__)
```

Reglas:

- Sin DB: correr comando inicial del proyecto. En Gestion de Carnicerias es `init_system`.
- Con DB y version distinta: correr solo migraciones.
- Con DB y misma version: no tocar la DB.
- Nunca usar `--reset` ni borrar datos en upgrades.
- El desinstalador puede preguntar si borrar datos, pero el instalador/upgrade no debe borrarlos.

### Doble instancia

Usa lock file con PID y valida con `psutil.pid_exists(pid)`. Si ya hay una instancia viva, solo abre el navegador y sale.

### Bandeja del sistema

Usa `pystray` para mantener vivo el proceso y permitir click derecho > Salir.

```python
menu = pystray.Menu(
    pystray.MenuItem("Abrir Gestion de Carnicerias", on_open),
    pystray.MenuItem(f"Version {__version__}", None, enabled=False),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("Salir", on_exit),
)
icon = pystray.Icon(APP_NAME, load_tray_image(), APP_NAME, menu)
icon.run()
```

---

## 4. Cambios necesarios en `settings.py`

La configuracion debe aceptar rutas por variables de entorno.

```python
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-development-key")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:8250,http://localhost:8250")
```

DB y media:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
    }
}

MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", BASE_DIR / "media")
```

Logs:

```python
LOG_DIR = Path(os.environ.get("LOG_DIR", BASE_DIR / "logs"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "gestion_de_carnicerias.log",
            "formatter": "standard",
            "encoding": "utf-8",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["file", "console"], "level": "INFO"},
}
```

En `urls.py`, servir media en modo desktop:

```python
from django.conf import settings
from django.conf.urls.static import static
import os

if settings.DEBUG or os.environ.get("GESTION_CARNICERIAS_DESKTOP") == "1":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## 5. `<app>.spec`

El `.spec` debe usar `run_server.py` como entrada.

Importante: en un spec de PyInstaller no uses `__file__` para calcular la raiz. Usa `SPECPATH`.

```python
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_ROOT = os.path.abspath(SPECPATH)
APP_NAME = "GestionDeCarnicerias"
ICON_FILE = os.path.join(PROJECT_ROOT, "static", "img", "ico.ico")
```

Incluir carpetas:

```python
DIRS_TO_INCLUDE = [
    "templates",
    "static",
    "staticfiles",
    "locale",
    os.path.join("pos", "templates"),
]

for directory in DIRS_TO_INCLUDE:
    source = os.path.join(PROJECT_ROOT, directory)
    if os.path.exists(source):
        datas.append((source, directory))
```

Incluir modulos de la app:

```python
APP_MODULES = ["gestion_de_carnicerias", "core", "tesoreria", "inventario", "compras", "ventas", "gastos", "pos"]

for module in APP_MODULES:
    hiddenimports += collect_submodules(module)
```

Hidden imports minimos:

```python
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
    "pystray",
    "reportlab",
]
```

Librerias complejas:

```python
for library in ["django", "jazzmin", "import_export", "openpyxl", "reportlab"]:
    library_datas, library_binaries, library_hiddenimports = collect_all(library)
    datas += library_datas
    binaries += library_binaries
    hiddenimports += library_hiddenimports
```

`console=False` es correcto, pero solo si `run_server.py` corrige streams como se mostro arriba.

---

## 6. `installer.nsi`

El instalador copia `dist\<App>\*` a `Program Files`, crea carpetas persistentes, da permisos, crea shortcuts, registra desinstalador y ejecuta migraciones/init mediante el exe.

Cabecera base:

```nsis
!define APP_NAME "GestionDeCarnicerias"
!define APP_EXE "GestionDeCarnicerias.exe"
!define APP_VERSION "1.0.0"
!define APP_BUILD "1.0.0.0"
!define COMPANY_NAME "Adema Sistemas"
!define DATA_ROOT "C:\GestionDeCarnicerias"
!define DB_DIR "C:\GestionDeCarnicerias\db"
!define LOG_DIR "C:\GestionDeCarnicerias\logs"
!define MEDIA_DIR "C:\GestionDeCarnicerias\media"
!define ICON_FILE "static\img\ico.ico"

Name "${APP_NAME}"
OutFile "${APP_NAME}_Installer_v${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
RequestExecutionLevel admin

VIProductVersion "${APP_BUILD}"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${COMPANY_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "${COMPANY_NAME}"
```

Permisos: no uses `Everyone`, porque depende del idioma de Windows. Usa el SID universal `*S-1-1-0`.

```nsis
CreateDirectory "${DATA_ROOT}"
CreateDirectory "${DB_DIR}"
CreateDirectory "${LOG_DIR}"
CreateDirectory "${MEDIA_DIR}"
nsExec::ExecToLog 'icacls "${DATA_ROOT}" /grant *S-1-1-0:(OI)(CI)F /T /C'
```

Durante instalacion/upgrade, ejecutar el exe en modo migracion:

```nsis
${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    nsExec::ExecToLog '"$INSTDIR\${APP_EXE}" --migrate-only'
${EndIf}
```

Esto no debe borrar DB. La logica de preservar datos vive en `run_server.py`.

---

## 7. `requirements_win.txt`

Archivo recomendado:

```text
asgiref==3.8.1
diff-match-patch==20241021
Django==5.2.3
django-import-export==4.3.8
django-jazzmin==3.0.1
django-solo==2.4.0
et_xmlfile==2.0.0
openpyxl==3.1.5
Pillow
psutil
psycopg2-binary
pyinstaller
pystray
python-dotenv==1.1.1
reportlab==4.4.10
sqlparse==0.5.3
tablib==3.8.0
tzdata==2025.2
```

Adapta la lista a cada proyecto. Si el `requirements.txt` original esta en una codificacion rara, crea este archivo en UTF-8 normal para evitar problemas de build.

---

## 8. `build_release.bat`

Usa `python -m PyInstaller`, no `pyinstaller` directo, para usar el PyInstaller del entorno activo.

Tambien evita poner la ruta `C:\Program Files (x86)\NSIS\makensis.exe` dentro de un bloque `if (...)` de batch sin cuidado: los parentesis de `(x86)` pueden romper el script. Usa labels.

Puntos obligatorios del script:

```bat
python -m pip install -r requirements_win.txt
python manage.py collectstatic --noinput --clear
python -m PyInstaller gestion_de_carnicerias.spec --clean --noconfirm
```

Deteccion robusta de NSIS:

```bat
set "MAKENSIS=makensis"
where makensis >nul 2>nul
if errorlevel 1 goto find_nsis
goto run_nsis

:find_nsis
if exist "C:\Program Files (x86)\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files (x86)\NSIS\makensis.exe"
if exist "C:\Program Files\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files\NSIS\makensis.exe"
if not exist "%MAKENSIS%" (
    echo No se encontro makensis.exe. Instala NSIS o agregalo al PATH.
    exit /b 1
)

:run_nsis
"%MAKENSIS%" installer.nsi
if errorlevel 1 exit /b 1
```

Archivado robusto:

```bat
set "INSTALLER=GestionDeCarnicerias_Installer_v%VERSION%.exe"
set "HASH_FILE=%INSTALLER%.sha256"
set "OUT_DIR=exe\%VERSION%"

if not exist "exe" mkdir "exe"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-FileHash '%INSTALLER%' -Algorithm SHA256 | ForEach-Object { $_.Hash } | Set-Content '%HASH_FILE%'"
copy /Y "%INSTALLER%" "%OUT_DIR%\%INSTALLER%"
copy /Y "%HASH_FILE%" "%OUT_DIR%\%HASH_FILE%"
```

---

## 9. Checklist para adaptar a cualquier app Django

1. Crear `version.py` con `__version__`.
2. Crear `up_version.py` y sincronizar `installer.nsi`.
3. Crear `run_server.py` con rutas persistentes, streams seguros, `ensure_django_ready()`, lock file, primer arranque, upgrades con `migrate --noinput` y tray icon.
4. Adaptar `settings.py` para leer `DB_NAME`, `MEDIA_ROOT`, `LOG_DIR`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
5. Adaptar `urls.py` para servir media cuando `GESTION_CARNICERIAS_DESKTOP=1` o equivalente.
6. Crear `<app>.spec` usando `SPECPATH`, `run_server.py`, `console=False`, icono, static, templates, locale y hidden imports.
7. Crear `installer.nsi` con permisos `icacls ... /grant *S-1-1-0:(OI)(CI)F`.
8. Crear `requirements_win.txt` en UTF-8.
9. Crear `build_release.bat` usando `python -m PyInstaller` y deteccion robusta de NSIS.
10. Probar instalacion limpia y upgrade con DB existente.

---

## 10. Pruebas recomendadas

### Django normal

```powershell
python manage.py check
python manage.py collectstatic --noinput --clear
```

### Streams sin consola y registry Django listo

```powershell
python -c "import sys; original_stdout=sys.stdout; sys.stdout=None; sys.stderr=None; import run_server; run_server.ensure_django_ready(); run_server.run_management_command(['check'], __import__('logging').getLogger('test')); original_stdout.write('call_command check ok\n')"
```

### Build

```powershell
.\build_release.bat
```

### Produccion

1. Instalar sin DB previa y confirmar que corre el comando inicial.
2. Verificar el cluster en `C:\<app>\pgdata` y que PostgreSQL escucha en `127.0.0.1:5433` mientras la app esta abierta.
3. Verificar log en `C:\<app>\logs\<app>.log`.
4. Abrir app desde shortcut.
5. Cerrar desde icono en bandeja.
6. Reinstalar una version nueva encima y confirmar que no borra la DB.

---

## Errores conocidos y solucion

### `AttributeError: 'NoneType' object has no attribute 'write'`

Causa: `console=False` deja `stdout/stderr` sin stream real.

Solucion: implementar `configure_standard_streams()` y pasar `stdout`/`stderr` explicitos en `call_command()`.

### `AppRegistryNotReady: The translation infrastructure cannot be initialized...`

Causa: `call_command()` ejecutado antes de `django.setup()`.

Solucion: implementar `ensure_django_ready()` y llamarlo antes de cualquier comando Django.

### `NameError: name '__file__' is not defined` en `.spec`

Causa: PyInstaller no garantiza `__file__` en specs.

Solucion: usar `PROJECT_ROOT = os.path.abspath(SPECPATH)`.

### `No se esperaba \NSIS\makensis.exe en este momento`

Causa: ruta `Program Files (x86)` dentro de un bloque batch con parentesis.

Solucion: usar variables entrecomilladas y labels `:find_nsis` / `:run_nsis`.

### Permisos fallan en Windows en otro idioma

Causa: usar `Everyone` en `icacls` depende del idioma.

Solucion: usar el SID universal `*S-1-1-0`.

### Upgrade pisa datos

Causa: correr setup inicial o reset aunque exista DB.

Solucion: si existe DB, nunca correr reset ni bootstrap destructivo; solo `migrate --noinput` cuando cambia la version.

---

## Notas finales

- `console=False` esta bien para UX final, pero exige streams seguros.
- `runserver` debe usar `use_reloader=False`.
- El server instalado escucha en `0.0.0.0:8250` para permitir acceso por QR desde celulares/tablets en la misma red local. La apertura automatica del navegador de la PC sigue usando `http://127.0.0.1:8250/pos/`.
- Los datos persistentes nunca viven en `Program Files`.
- `installed_version.txt` es la marca de migracion por version.
- El instalador puede ejecutar `--migrate-only`, pero la decision de inicializar o migrar vive en `run_server.py`.
- La advertencia NSIS `LegalCopyright` se evita agregando `VIAddVersionKey "LegalCopyright" "<Empresa>"`.