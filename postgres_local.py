"""
PostgreSQL propio de la app de escritorio.

La PC de la sucursal no necesita un PostgreSQL instalado aparte: el instalador
trae los binarios en ``<instalación>\\pgsql`` y la app crea su propio cluster
en ``C:\\GestionDeCarnicerias\\pgdata``, que escucha solo en 127.0.0.1:5433.
El 5432 queda libre por si la PC ya tiene otro PostgreSQL.

La clave del usuario de la base se genera la primera vez y queda en la
carpeta de datos; nunca viaja a la central.
"""

import secrets
import subprocess
from pathlib import Path

PUERTO = 5433
USUARIO = 'carnicerias'
BASE = 'gestion_de_carnicerias'
SIN_VENTANA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class PostgresError(RuntimeError):
    """No se pudo preparar o arrancar el PostgreSQL local; el mensaje va al log."""


def buscar_binarios(candidatos):
    """Primera carpeta de la lista que tenga ``bin\\pg_ctl.exe``."""
    for candidato in candidatos:
        if candidato and (Path(candidato) / 'bin' / 'pg_ctl.exe').exists():
            return Path(candidato)
    raise PostgresError('No se encontraron los binarios de PostgreSQL (pgsql\\bin\\pg_ctl.exe).')


class PostgresLocal:
    def __init__(self, pgsql_dir, data_dir, log_path, clave_path, puerto=PUERTO):
        self.pgsql = Path(pgsql_dir)
        self.data = Path(data_dir)
        self.log_path = Path(log_path)
        self.clave_path = Path(clave_path)
        self.puerto = puerto

    def _bin(self, nombre):
        return str(self.pgsql / 'bin' / f'{nombre}.exe')

    def _correr(self, args, timeout=120):
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=SIN_VENTANA)
        if r.returncode != 0:
            detalle = (r.stderr or r.stdout or '').strip()[-800:]
            raise PostgresError(f'{Path(args[0]).name} terminó con código {r.returncode}: {detalle}')
        return r.stdout

    def clave(self):
        if not self.clave_path.exists():
            self.clave_path.parent.mkdir(parents=True, exist_ok=True)
            self.clave_path.write_text(secrets.token_urlsafe(24), encoding='utf-8')
        return self.clave_path.read_text(encoding='utf-8').strip()

    def version_binarios(self):
        """Versión mayor de los binarios: 'pg_ctl (PostgreSQL) 18.1' → '18'."""
        return self._correr([self._bin('pg_ctl'), '--version']).split()[-1].split('.')[0]

    def inicializado(self):
        return (self.data / 'PG_VERSION').exists()

    def inicializar(self):
        """Crea el cluster con autenticación por clave y lo deja escuchando solo en 127.0.0.1."""
        self.data.parent.mkdir(parents=True, exist_ok=True)
        archivo_clave = self.data.parent / 'pwfile.tmp'
        archivo_clave.write_text(self.clave(), encoding='utf-8')
        try:
            self._correr([
                self._bin('initdb'), '-D', str(self.data), '-U', USUARIO, '-A', 'scram-sha-256',
                '--pwfile', str(archivo_clave), '-E', 'UTF8', '--no-locale',
            ], timeout=300)
        finally:
            archivo_clave.unlink(missing_ok=True)
        with (self.data / 'postgresql.conf').open('a', encoding='utf-8') as conf:
            conf.write(f"\n# Gestion de Carnicerias\nlisten_addresses = '127.0.0.1'\nport = {self.puerto}\n")

    def corriendo(self):
        r = subprocess.run([self._bin('pg_ctl'), 'status', '-D', str(self.data)],
                           capture_output=True, text=True, creationflags=SIN_VENTANA)
        return r.returncode == 0

    def arrancar(self):
        """Arranca el servidor si no estaba corriendo. Devuelve True si lo arrancó esta llamada."""
        if not self.inicializado():
            self.inicializar()
        version_datos = (self.data / 'PG_VERSION').read_text(encoding='utf-8').strip()
        version_bin = self.version_binarios()
        if version_datos != version_bin:
            raise PostgresError(
                f'Los datos son de PostgreSQL {version_datos} y los binarios instalados son {version_bin}: '
                'hace falta pg_upgrade antes de actualizar.')
        if self.corriendo():
            return False
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Sin capturar la salida: el postmaster hereda los pipes y subprocess esperaría para siempre.
        r = subprocess.run([self._bin('pg_ctl'), 'start', '-D', str(self.data), '-l', str(self.log_path), '-w', '-t', '60'],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=90, creationflags=SIN_VENTANA)
        if r.returncode != 0:
            raise PostgresError(f'PostgreSQL no arrancó. Ver {self.log_path}.')
        return True

    def detener(self):
        if self.inicializado() and self.corriendo():
            self._correr([self._bin('pg_ctl'), 'stop', '-D', str(self.data), '-m', 'fast', '-w'], timeout=90)

    def entorno(self):
        """Variables DB_* que lee settings.py."""
        return {
            'DB_NAME': BASE, 'DB_USER': USUARIO, 'DB_PASSWORD': self.clave(),
            'DB_HOST': '127.0.0.1', 'DB_PORT': str(self.puerto),
        }

    def asegurar_base(self):
        """Crea la base de la app si el cluster todavía no la tiene."""
        import psycopg2

        con = psycopg2.connect(host='127.0.0.1', port=self.puerto, user=USUARIO, password=self.clave(), dbname='postgres')
        try:
            con.autocommit = True
            with con.cursor() as cur:
                cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [BASE])
                if cur.fetchone() is None:
                    cur.execute(f"CREATE DATABASE {BASE} ENCODING 'UTF8' TEMPLATE template0")
        finally:
            con.close()


def base_migrada(entorno):
    """True si la base ya tiene las tablas de Django (se corrió init_system alguna vez)."""
    import psycopg2

    con = psycopg2.connect(host=entorno['DB_HOST'], port=entorno['DB_PORT'], user=entorno['DB_USER'],
                           password=entorno['DB_PASSWORD'], dbname=entorno['DB_NAME'])
    try:
        with con.cursor() as cur:
            cur.execute("SELECT to_regclass('public.django_migrations') IS NOT NULL")
            return cur.fetchone()[0]
    finally:
        con.close()
