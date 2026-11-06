#!/usr/bin/env bash
# (Re)crea las dos bases de DEMO con datos de ejemplo, desde cero:
#   gestion_de_carnicerias_demo          → la PC de la sucursal "S001 · Centro" (puerto 8765)
#   gestion_de_carnicerias_demo_central  → el frigorífico, con tres sucursales (puerto 8766)
# Todos los datos son inventados (seed_carniceria). No lee ni toca la base real.
#   uso:  bash documentacion/_herramientas/demo/reset_demo.sh [--solo-sucursal]
set -e
source "$(dirname "$0")/entorno.sh" || exit 1
cd "$RAIZ"
SUC=gestion_de_carnicerias_demo
CEN=gestion_de_carnicerias_demo_central

recrear() {   # $1 = base (tiene que contener "demo")
  case "$1" in *demo*) ;; *) echo "ERROR: '$1' no contiene demo"; exit 1;; esac
  psql -h "$DB_HOST" -d postgres -w -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$1' AND pid<>pg_backend_pid();" >/dev/null
  psql -h "$DB_HOST" -d postgres -w -q -c "DROP DATABASE IF EXISTS \"$1\";"
  psql -h "$DB_HOST" -d postgres -w -q -c "CREATE DATABASE \"$1\" ENCODING 'UTF8';"
}

echo "== Base de la sucursal: $SUC"
rm -rf "$DEMO_DIR/media"; mkdir -p "$DEMO_DIR/media/productos"
cp "$RAIZ"/media/productos/*-ia.jpg "$DEMO_DIR/media/productos/" 2>/dev/null || true
recrear $SUC
export DB_NAME=$SUC SYNC_MODO=sucursal
$DEMO_PY manage.py init_system >/dev/null
$DEMO_PY documentacion/_herramientas/demo/preparar_demo.py antes-del-seed
$DEMO_PY manage.py seed_carniceria
$DEMO_PY documentacion/_herramientas/demo/preparar_demo.py despues-del-seed
[ "${1:-}" = "--solo-sucursal" ] && exit 0

echo "== Base de la central: $CEN (copia de la sucursal + dos sucursales más)"
recrear $CEN
psql -h "$DB_HOST" -d postgres -w -q -c "DROP DATABASE \"$CEN\";"
psql -h "$DB_HOST" -d postgres -w -q -c "CREATE DATABASE \"$CEN\" TEMPLATE \"$SUC\";"
export DB_NAME=$CEN SYNC_MODO=central
$DEMO_PY documentacion/_herramientas/demo/preparar_demo.py central
echo "== Listo"
