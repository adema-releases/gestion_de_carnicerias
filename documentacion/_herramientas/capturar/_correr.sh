#!/usr/bin/env bash
# Corre varios scripts de captura en serie. Uso:
#   bash _correr.sh t03_armar_una_comanda t04_mis_comandas_y_anular        (en español)
#   DOC_LANG=zh bash _correr.sh t03_armar_una_comanda                      (en chino)
cd "$(dirname "$0")/../../.."
for t in "$@"; do
  echo "== ${DOC_LANG:-es} · $t"
  timeout 300 node "documentacion/_herramientas/capturar/${t%.js}.js" 2>&1 | tail -12
done
echo "== FIN"
