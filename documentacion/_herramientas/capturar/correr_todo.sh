#!/usr/bin/env bash
# Rehace TODAS las capturas de los tutoriales, en el orden correcto, partiendo de una demo limpia.
#
# Antes: los dos servidores de demo tienen que estar arriba (en otras terminales):
#     bash documentacion/_herramientas/demo/levantar.sh            → sucursal  http://127.0.0.1:8765
#     bash documentacion/_herramientas/demo/levantar.sh central    → central   http://127.0.0.1:8766
#
# Uso:  bash documentacion/_herramientas/capturar/correr_todo.sh          (español y chino)
#       bash documentacion/_herramientas/capturar/correr_todo.sh es       (solo español)
#       bash documentacion/_herramientas/capturar/correr_todo.sh zh       (solo chino)
#
# El orden importa: cada tutorial que modifica datos deja el estado que necesita el siguiente.
#   1. ingreso e idioma (01-02)               solo lectura
#   2. mostrador (03-04)                      deja una comanda abierta para la caja
#   3. caja (06-09), cierre (10), apertura (05)
#   4. liquidación del martes (15-16), recepción del despacho y desposte (11-14), conteo de control (17)
#   5. gerente en el admin (18-22)
#   6. central del frigorífico (23-27)
set -u
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$RAIZ"
CAP=documentacion/_herramientas/capturar
DEMO=documentacion/_herramientas/demo
IDIOMAS="${1:-es zh}"

for url in http://127.0.0.1:8765 http://127.0.0.1:8766; do
  curl -s -o /dev/null "$url/accounts/login/" || { echo "El servidor $url no está arriba. Ver el encabezado de este script."; exit 1; }
done

for idioma in $IDIOMAS; do
  echo "################ $idioma"
  bash $DEMO/reset_demo.sh || exit 1
  export DOC_LANG=$idioma
  correr() { bash $CAP/_correr.sh "$@"; }
  correr t01_ingresar_y_elegir_puesto t02_cambiar_idioma
  correr t03_armar_una_comanda t04_mis_comandas_y_anular
  correr t06_cobrar_una_comanda t07_venta_por_unidad_y_pago_dividido t08_fiado_y_cobro_de_deuda t09_gastos_y_retiros \
         t10_cerrar_la_caja t05_abrir_la_caja
  correr t15_liquidacion_semanal_contar t16_liquidacion_cerrar \
         t11_recibir_despacho_del_frigorifico t12_recibir_de_otro_proveedor t13_camara_y_desposte t14_ver_el_stock \
         t17_conteo_de_control
  correr t18_alta_de_personal t19_puestos_camaras_y_configuracion t20_medios_de_pago_de_la_cajera \
         t21_dashboard_y_reportes t22_controles_de_la_semana
  correr t23_panel_central t24_despachar_a_una_sucursal t25_cuenta_corriente_de_sucursales \
         t26_catalogo_precios_y_plantillas t27_abrir_una_sucursal_nueva
done
# deja la demo limpia y en español
bash $DEMO/reset_demo.sh >/dev/null
echo "== LISTO. Revisá a ojo las imágenes marcadas con «~ revisar a ojo» en los registros."
