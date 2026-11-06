#!/usr/bin/env bash
# Levanta el sistema de DEMO.
#   Sucursal:  bash levantar.sh                      → http://127.0.0.1:8765  (base gestion_de_carnicerias_demo)
#   Central:   bash levantar.sh central              → http://127.0.0.1:8766  (base gestion_de_carnicerias_demo_central)
# manage.py fija el puerto con RUNSERVER_PORT (ignora el que se pase a runserver).
if [ "${1:-}" = "central" ]; then
  export DEMO_MODO=central DEMO_DB=gestion_de_carnicerias_demo_central DEMO_PORT=8766
fi
source "$(dirname "$0")/entorno.sh" || exit 1
cd "$RAIZ"
export RUNSERVER_PORT=${DEMO_PORT:-8765}
exec $DEMO_PY -u manage.py runserver --noreload
