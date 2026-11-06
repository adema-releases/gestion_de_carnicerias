# Entorno de DEMO para generar documentación y capturas.
# Apunta a una base `*_demo` con datos de ejemplo (seed_carniceria) y a un MEDIA propio. NUNCA a la base real.
#   uso:  source documentacion/_herramientas/demo/entorno.sh
#   variables opcionales: DEMO_DB (base), DEMO_MODO (sucursal | central)
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEMO_DIR="$RAIZ/documentacion/_herramientas/demo"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PGCLIENTENCODING=UTF8
# Las variables exportadas acá pisan a las del .env (python-dotenv no sobrescribe lo ya definido).
export DB_NAME="${DEMO_DB:-gestion_de_carnicerias_demo}"
export DB_HOST="${DEMO_DB_HOST:-localhost}"
export SYNC_MODO="${DEMO_MODO:-sucursal}"
export SYNC_URL=""            # la demo nunca sincroniza con nadie
export SYNC_TOKEN=""
export MEDIA_ROOT="$(cygpath -m "$DEMO_DIR/media" 2>/dev/null || echo "$DEMO_DIR/media")"
export LOG_DIR="$(cygpath -m "$DEMO_DIR/logs" 2>/dev/null || echo "$DEMO_DIR/logs")"
mkdir -p "$DEMO_DIR/media" "$DEMO_DIR/logs"
export DEBUG=True
export ALLOWED_HOSTS="localhost,127.0.0.1"
export CSRF_TRUSTED_ORIGINS="http://127.0.0.1:8765,http://localhost:8765,http://127.0.0.1:8766,http://localhost:8766"
export DEMO_PY="$RAIZ/venv/Scripts/python.exe"
# Clave de PostgreSQL: la misma del .env del proyecto (solo para crear/borrar la base de demo).
export PGPASSWORD="$(grep -E '^DB_PASSWORD=' "$RAIZ/.env" | cut -d= -f2- | tr -d '\r')"
export PGUSER="$(grep -E '^DB_USER=' "$RAIZ/.env" | cut -d= -f2- | tr -d '\r')"
case "$DB_NAME" in *demo*) ;; *) echo "ERROR: DB_NAME ('$DB_NAME') no contiene 'demo'. Abortando."; return 1 2>/dev/null || exit 1;; esac
