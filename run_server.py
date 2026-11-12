#!/usr/bin/env python
import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import psutil
import django
from django.apps import apps
from django.core.management import call_command
from dotenv import load_dotenv

from postgres_local import PostgresLocal, base_migrada, buscar_binarios
from version import __version__


APP_NAME = "GestionDeCarnicerias"
PROJECT_NAME = "gestion_de_carnicerias"
# GDC_PORT y GDC_DATA_ROOT existen para probar el runtime sin pisar una instalación real.
PORT = int(os.environ.get("GDC_PORT", "8250"))
LOCAL_URL = f"http://127.0.0.1:{PORT}/pos/"

DATA_ROOT = Path(os.environ.get("GDC_DATA_ROOT", r"C:\GestionDeCarnicerias"))
DB_DIR = DATA_ROOT / "db"
LOG_DIR = DATA_ROOT / "logs"
MEDIA_DIR = DATA_ROOT / "media"
PG_DATA_DIR = DATA_ROOT / "pgdata"
PG_CLAVE_PATH = DB_DIR / "clave_postgres.txt"
PG_LOG_PATH = LOG_DIR / "postgres.log"
CONFIG_PATH = DATA_ROOT / "config.env"
LOG_PATH = LOG_DIR / "gestion_de_carnicerias.log"
LOCK_PATH = DATA_ROOT / "gestion_de_carnicerias.lock"
INSTALLED_VERSION_PATH = DATA_ROOT / "installed_version.txt"
_STDOUT_LOG_HANDLE = None
_CONFIG_CARGADA = False
_POSTGRES = None
_BASE_EXTERNA = None

CONFIG_INICIAL = """\
# Configuracion de esta PC (Gestion de Carnicerias).
# Se lee al arrancar: despues de cambiarla, cerra la app desde la bandeja y abrila de nuevo.

# Sincronizacion con la central del frigorifico.
# La URL y el token salen del admin de la central (Core -> Sucursales).
SYNC_MODO=sucursal
SYNC_URL=
SYNC_TOKEN=

# Base de datos: si DB_HOST queda comentado, la app usa su propio PostgreSQL (recomendado).
# Para usar un PostgreSQL ya instalado en la PC, descomenta y completa:
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=gestion_de_carnicerias
# DB_USER=
# DB_PASSWORD=
"""


def resource_path(*parts):
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir.joinpath(*parts)


def ensure_runtime_dirs():
    for path in (DATA_ROOT, DB_DIR, LOG_DIR, MEDIA_DIR):
        path.mkdir(parents=True, exist_ok=True)


def cargar_config_pc():
    """Lee config.env de la carpeta de datos (lo crea la primera vez). Gana sobre cualquier otro .env."""
    global _CONFIG_CARGADA
    if _CONFIG_CARGADA:
        return
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(CONFIG_INICIAL, encoding="utf-8")
    load_dotenv(CONFIG_PATH, override=True)
    _CONFIG_CARGADA = True


def pgsql_candidatos():
    candidatos = [os.environ.get("GDC_PGSQL_DIR")]
    if getattr(sys, "frozen", False):
        candidatos.append(Path(sys.executable).parent / "pgsql")   # lo copia el instalador
    candidatos.append(Path(__file__).resolve().parent / "vendor" / "pgsql")
    return candidatos


def preparar_entorno_base():
    """Decide una sola vez qué base usa la app y deja las variables DB_* listas para settings.py.

    Sin DB_HOST en config.env, la app usa su propio PostgreSQL y devuelve ese
    servidor; con DB_HOST, usa el servidor indicado y devuelve None.
    """
    global _POSTGRES, _BASE_EXTERNA
    if _BASE_EXTERNA is None:
        _BASE_EXTERNA = bool(os.environ.get("DB_HOST"))
        if not _BASE_EXTERNA:
            _POSTGRES = PostgresLocal(buscar_binarios(pgsql_candidatos()), PG_DATA_DIR, PG_LOG_PATH, PG_CLAVE_PATH)
            os.environ.update(_POSTGRES.entorno())
    return _POSTGRES


def entorno_base():
    """Las DB_* con los mismos valores por defecto que settings.py."""
    return {
        "DB_NAME": os.environ.get("DB_NAME", "gestion_de_carnicerias"),
        "DB_USER": os.environ.get("DB_USER", "kevin"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "DB_HOST": os.environ.get("DB_HOST", "localhost"),
        "DB_PORT": os.environ.get("DB_PORT", "5432"),
    }


def detener_postgres(logger):
    if _POSTGRES is None:
        return
    try:
        _POSTGRES.detener()
        logger.info("PostgreSQL local detenido")
    except Exception:
        logger.exception("No se pudo detener PostgreSQL local")


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


def configure_logging():
    ensure_runtime_dirs()
    configure_standard_streams()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(APP_NAME)


def get_lan_ip():
    """Devuelve la IP de LAN de la máquina, o None si no se puede determinar."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_lan_url():
    lan_ip = get_lan_ip()
    if not lan_ip:
        return None
    return f"http://{lan_ip}:{PORT}/pos/"


def configure_environment():
    ensure_runtime_dirs()
    configure_standard_streams()
    cargar_config_pc()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"{PROJECT_NAME}.settings")
    os.environ["GESTION_CARNICERIAS_DESKTOP"] = "1"
    preparar_entorno_base()
    os.environ["MEDIA_ROOT"] = str(MEDIA_DIR)
    os.environ["LOG_DIR"] = str(LOG_DIR)
    os.environ.setdefault("SECRET_KEY", "django-insecure-gestion-de-carnicerias-local-runtime-key")
    os.environ.setdefault("DEBUG", "False")
    os.environ.setdefault("ALLOWED_HOSTS", "*")
    trusted = f"http://127.0.0.1:{PORT},http://localhost:{PORT}"
    lan_ip = get_lan_ip()
    if lan_ip:
        trusted += f",http://{lan_ip}:{PORT}"
    os.environ.setdefault("CSRF_TRUSTED_ORIGINS", trusted)


def ensure_django_ready():
    configure_environment()
    if not apps.ready:
        django.setup()


def iniciar_base(logger):
    """Arranca el PostgreSQL propio si corresponde y crea la base. Devuelve True si lo arrancó esta llamada."""
    postgres = preparar_entorno_base()
    if postgres is None:
        logger.info("Usando el PostgreSQL indicado en %s", CONFIG_PATH)
        return False
    if not postgres.inicializado():
        logger.info("Creando el PostgreSQL local en %s", PG_DATA_DIR)
    arrancado = postgres.arrancar()
    postgres.asegurar_base()
    logger.info("PostgreSQL local %s en 127.0.0.1:%s", "arrancado" if arrancado else "ya estaba corriendo", postgres.puerto)
    return arrancado


def is_database_present():
    return base_migrada(entorno_base())


def read_installed_version():
    if not INSTALLED_VERSION_PATH.exists():
        return None
    return INSTALLED_VERSION_PATH.read_text(encoding="utf-8").strip() or None


def write_installed_version():
    INSTALLED_VERSION_PATH.write_text(__version__, encoding="utf-8", newline="\n")


def run_management_command(args, logger):
    logger.info("Ejecutando manage.py %s", " ".join(args))
    ensure_django_ready()
    command_stream = get_command_stream()
    command_args = [arg for arg in args[1:] if arg != "--noinput"]
    command_options = {"stdout": command_stream, "stderr": command_stream}
    if "--noinput" in args:
        command_options["interactive"] = False
    call_command(args[0], *command_args, **command_options)


def bootstrap_database(logger):
    """Deja la base lista (creada o migrada). Devuelve True si arrancó el PostgreSQL local."""
    configure_environment()
    arrancado = iniciar_base(logger)
    database_exists = is_database_present()
    installed_version = read_installed_version()

    if not database_exists:
        logger.info("No se detecto base de datos. Inicializando Gestion de Carnicerias %s", __version__)
        run_management_command(["init_system"], logger)
        write_installed_version()
        return arrancado

    logger.info(
        "Verificando migraciones pendientes sobre base existente (version registrada: %s, runtime: %s)",
        installed_version or "desconocida",
        __version__,
    )
    run_management_command(["migrate", "--noinput"], logger)

    if installed_version != __version__:
        logger.info(
            "Actualizando version instalada de %s a %s",
            installed_version or "desconocida",
            __version__,
        )
    else:
        logger.info("Base de datos migrada y verificada para Gestion de Carnicerias %s", __version__)

    write_installed_version()
    return arrancado


def read_lock_pid():
    if not LOCK_PATH.exists():
        return None
    try:
        return int(LOCK_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def ensure_single_instance(logger):
    pid = read_lock_pid()
    if pid and psutil.pid_exists(pid):
        logger.info("Gestion de Carnicerias ya esta corriendo con PID %s. Abriendo navegador.", pid)
        webbrowser.open(LOCAL_URL)
        return False

    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8", newline="\n")
    return True


def remove_lock_file():
    try:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()
    except OSError:
        pass


def run_django_server(logger):
    configure_environment()
    try:
        ensure_django_ready()
        command_stream = get_command_stream()
        call_command(
            "runserver",
            f"0.0.0.0:{PORT}",
            use_reloader=False,
            insecure_serving=True,
            stdout=command_stream,
            stderr=command_stream,
        )
    except Exception:
        logger.exception("El servidor Django se detuvo por un error")


SYNC_INTERVALO_SEG = 60


def run_sync_loop(logger):
    """Sincroniza con la central cada minuto si SYNC_URL y SYNC_TOKEN están configurados.

    Sin internet solo deja el error en el log: la cola espera y la sucursal sigue vendiendo.
    """
    from django.conf import settings

    if not (settings.SYNC_URL and settings.SYNC_TOKEN):
        logger.info("Sincronización desactivada: falta SYNC_URL o SYNC_TOKEN")
        return
    from core.agente_sync import sincronizar
    from core.sincronizacion import SyncError

    while True:
        try:
            r = sincronizar()
            logger.info("Sincronizado: subidos %s, bajados %s", r["subidos"], r["bajados"])
        except SyncError as exc:
            logger.warning("No se pudo sincronizar: %s", exc)
        except Exception:
            logger.exception("Error inesperado al sincronizar")
        time.sleep(SYNC_INTERVALO_SEG)


def load_tray_image():
    from PIL import Image

    icon_path = resource_path("static", "img", "ico.ico")
    if icon_path.exists():
        return Image.open(icon_path)
    return Image.new("RGB", (64, 64), color=(24, 80, 160))


def run_tray(logger):
    import pystray

    def on_open(icon, item):
        webbrowser.open(LOCAL_URL)

    def on_exit(icon, item):
        logger.info("Cerrando Gestion de Carnicerias desde bandeja del sistema")
        detener_postgres(logger)
        remove_lock_file()
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir Gestion de Carnicerias", on_open),
        pystray.MenuItem(f"Version {__version__}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_exit),
    )
    icon = pystray.Icon(APP_NAME, load_tray_image(), APP_NAME, menu)
    icon.run()


def run_desktop_app():
    logger = configure_logging()
    configure_environment()
    lan_url = get_lan_url()

    if not ensure_single_instance(logger):
        return 0

    try:
        bootstrap_database(logger)
        server_thread = threading.Thread(target=run_django_server, args=(logger,), daemon=True)
        server_thread.start()
        threading.Thread(target=run_sync_loop, args=(logger,), daemon=True).start()
        time.sleep(2)
        webbrowser.open(LOCAL_URL)
        logger.info("Gestion de Carnicerias iniciado en %s", LOCAL_URL)
        if lan_url:
            logger.info("Acceso desde otros dispositivos en la misma red: %s", lan_url)
        run_tray(logger)
    finally:
        detener_postgres(logger)
        remove_lock_file()
    return 0


def run_server_only():
    """Base, sincronización y servidor en primer plano, sin bandeja ni navegador (Ctrl+C para salir)."""
    logger = configure_logging()
    if not ensure_single_instance(logger):
        return 1
    try:
        bootstrap_database(logger)
        threading.Thread(target=run_sync_loop, args=(logger,), daemon=True).start()
        logger.info("Gestion de Carnicerias sirviendo en %s", LOCAL_URL)
        run_django_server(logger)
    finally:
        detener_postgres(logger)
        remove_lock_file()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Gestion de Carnicerias desktop runtime")
    parser.add_argument("--version", action="store_true", help="Muestra la version y finaliza")
    parser.add_argument("--migrate-only", action="store_true", help="Aplica init/migrate y finaliza")
    parser.add_argument("--servidor", action="store_true", help="Corre sin bandeja ni navegador, en primer plano")
    parser.add_argument("--alta-frigorifico-uno", "--alta-catan", dest="alta_catan", action="store_true",
                        help="Prepara la base y carga los datos de Frigorífico Uno (seed_frigorifico_uno)")
    parser.add_argument("--exportar-base", action="store_true",
                        help="Guarda un respaldo completo (datos y fotos) en la carpeta respaldos y la abre")
    args = parser.parse_args()

    if args.version:
        print(__version__)
        return 0

    logger = configure_logging()
    if args.alta_catan:
        arrancado = bootstrap_database(logger)
        try:
            run_management_command(["seed_frigorifico_uno"], logger)
        finally:
            if arrancado:
                detener_postgres(logger)
        return 0
    if args.exportar_base:
        # Funciona con la app abierta o cerrada: si el PostgreSQL lo arranca esta llamada, lo apaga al terminar.
        arrancado = bootstrap_database(logger)
        try:
            run_management_command(["exportar_base"], logger)
        finally:
            if arrancado:
                detener_postgres(logger)
        carpeta = DATA_ROOT / "respaldos"
        if carpeta.is_dir() and hasattr(os, "startfile"):
            os.startfile(carpeta)   # muestra el .zip recién hecho
        return 0
    if args.migrate_only:
        if bootstrap_database(logger):
            detener_postgres(logger)   # lo arrancó esta llamada: la app no está abierta
        return 0
    if args.servidor:
        return run_server_only()

    return run_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())