# Ajustes implementados en adelantos automaticos

## Objetivo del ajuste

Aplicar la regla de negocio pedida para adelantos automaticos y conciliacion manual:

- un adelanto solo debe cancelar una deuda si alcanza para cubrirla completa
- si no alcanza para la siguiente deuda en orden cronologico, no debe aplicarse parcialmente
- el remanente debe quedar como saldo a favor disponible

## Ajuste adicional (2026-06-06): estrategia configurable de auto compensacion

Se agrego una nueva opcion en `Configuracion`:

- `compensar_deudas_mas_antiguas_primero` (default: `True`)

Comportamiento:

- Si esta en `True`: se mantiene el orden cronologico estricto (comportamiento previo).
- Si esta en `False`: en autoaplicado puede saltear deudas antiguas que no se puedan cubrir completas y compensar deudas posteriores que si queden cubiertas completas.
- En ambos casos no se habilitan aplicaciones parciales.

## Cambios implementados

### 1. Regla unica de seleccion de deudas cubiertas

Se agrego una funcion comun en `pos/views.py`:

- `_seleccionar_deudas_cubiertas_por_adelanto(...)`

Esta funcion recorre las deudas en orden cronologico y solo devuelve aquellas que pueden ser cubiertas completamente con el remanente del adelanto.

Regla aplicada:

```python
if remanente_adelanto < saldo:
    break
```

Eso reemplaza el criterio anterior basado en aplicaciones parciales con `min(saldo, remanente)`.

### 2. Autoaplicado de clientes endurecido

Se actualizo `pos/views.py` en:

- `_intentar_cobro_automatico_por_adelanto(...)`

Nuevo comportamiento:

- cancela solo deudas de cliente totalmente cubiertas
- si el remanente no alcanza para la siguiente deuda, no la toca
- el saldo restante queda como adelanto disponible
- si existen varios adelantos disponibles, usa el saldo a favor acumulado del cliente para decidir la cancelacion
- al aplicar la cancelacion, distribuye el consumo real entre los adelantos disponibles en orden cronologico
- ahora la estrategia de seleccion depende de `compensar_deudas_mas_antiguas_primero`

### 3. Autoaplicado de proveedores endurecido

Se actualizo `pos/views.py` en:

- `_intentar_pago_automatico_por_adelanto_proveedor(...)`

Nuevo comportamiento:

- cancela solo deudas de proveedor totalmente cubiertas
- no hace aplicaciones parciales sobre compras o saldos iniciales
- conserva el remanente como adelanto disponible
- si existen varios adelantos disponibles, usa el saldo a favor acumulado del proveedor para decidir la cancelacion
- al aplicar la cancelacion, distribuye el consumo real entre los adelantos disponibles en orden cronologico
- ahora la estrategia de seleccion depende de `compensar_deudas_mas_antiguas_primero`

### 4. Conciliacion manual de clientes alineada

Se actualizo `pos/views.py` en:

- `api_cliente_cc_conciliar_manual(...)`

Nuevo comportamiento:

- usa la misma regla estricta que el autoaplicado
- solo genera cobros manuales por deudas completamente cubiertas
- combina todos los adelantos disponibles del cliente antes de decidir si una deuda puede conciliarse

### 5. Conciliacion manual de proveedores alineada

Se actualizo `pos/views.py` en:

- `api_proveedor_cc_conciliar_manual(...)`

Nuevo comportamiento:

- usa la misma regla estricta que el autoaplicado
- solo genera cancelaciones manuales por deudas completamente cubiertas
- combina todos los adelantos disponibles del proveedor antes de decidir si una deuda puede conciliarse

### 6. Ticket de estado de cuenta mas claro

Se actualizo `pos/printing.py` en:

- `build_estado_cuenta_ticket(...)`

Nuevo comportamiento:

- cada deuda pendiente imprime el identificador del ticket o saldo inicial
- muestra `Original` con la deuda original
- muestra `Pendiente` con el saldo pendiente actual

Con esto el comprobante deja de resumir cada deuda solo con el saldo neto y pasa a diferenciar claramente el importe original del pendiente remanente.

### 7. Nuevo reporte de adelantos recibidos

Se agrego un nuevo reporte exclusivo para clientes:

- boton `Adelantos recibidos` en el modal de cuenta corriente del cliente
- endpoint `api_cliente_adelantos_recibidos_excel(...)`
- generador Excel `_cliente_adelantos_recibidos_excel(...)`

Nuevo comportamiento:

- exporta unicamente los adelantos recibidos del cliente seleccionado
- muestra monto recibido, aplicado y disponible por cada adelanto
- si un adelanto se uso para compensar compras, agrega a la derecha las referencias `Venta #...`

Para soportarlo, cada adelanto del cliente ahora incluye tambien:

- `ventas_compensadas`
- `ventas_compensadas_label`

## Comportamiento final esperado

### Modo configurable de autoaplicado

- `compensar_deudas_mas_antiguas_primero = True`: no saltea deudas anteriores no cubribles.
- `compensar_deudas_mas_antiguas_primero = False`: permite saltear deudas anteriores no cubribles para compensar deudas posteriores cubiertas completas.

### Cliente

Si un cliente tiene:

- deuda 1: `1000`
- deuda 2: `1500`
- adelanto: `2000`

El sistema ahora hace esto:

- cancela la deuda 1 completa
- no toca la deuda 2
- deja `1000` como adelanto disponible

Si un cliente tiene:

- adelanto 1 disponible: `100`
- adelanto 2 disponible: `100`
- deuda pendiente: `200`

El sistema ahora hace esto:

- combina ambos adelantos para evaluar la cancelacion
- cancela la deuda completa
- consume los adelantos en orden cronologico

### Proveedor

Si un proveedor tiene:

- deuda 1: `3000`
- deuda 2: `2000`
- adelanto: `4000`

El sistema ahora hace esto:

- cancela la deuda 1 completa
- no toca la deuda 2
- deja `1000` como adelanto disponible

Si un proveedor tiene:

- adelanto 1 disponible: `100`
- adelanto 2 disponible: `100`
- deuda pendiente: `200`

El sistema ahora hace esto:

- combina ambos adelantos para evaluar la cancelacion
- cancela la deuda completa
- consume los adelantos en orden cronologico

## Archivos modificados

- `pos/views.py`
- `core/models.py`
- `core/migrations/0012_configuracion_compensar_deudas_mas_antiguas_primero.py`
- `pos/urls.py`
- `pos/templates/pos/terminal.html`
- `pos/printing.py`
- `pos/tests.py`

## Tests actualizados y agregados

Se actualizaron expectativas existentes y se agrego cobertura nueva para conciliacion manual.

Tests validados:

- `test_cobro_automatico_deudas_por_adelanto`
- `test_cobro_automatico_combina_varios_adelantos_para_cancelar_deuda`
- `test_pago_automatico_deudas_proveedor_por_adelanto`
- `test_pago_automatico_proveedor_combina_varios_adelantos_para_cancelar_deuda`
- `test_conciliacion_manual_cliente_solo_cancela_deudas_completas`
- `test_conciliacion_manual_cliente_combina_varios_adelantos`
- `test_conciliacion_manual_proveedor_solo_cancela_deudas_completas`
- `test_conciliacion_manual_proveedor_combina_varios_adelantos`
- `test_imprimir_ticket_cc_cliente`
- `test_exportar_excel_de_adelantos_recibidos_cliente`

## Validacion ejecutada

Se ejecutaron estos tests puntuales:

```powershell
.\venv\Scripts\python.exe manage.py test \
  pos.tests.SaldosInicialesPosTests.test_cobro_automatico_deudas_por_adelanto \
  pos.tests.SaldosInicialesPosTests.test_pago_automatico_deudas_proveedor_por_adelanto \
  pos.tests.SaldosInicialesPosTests.test_conciliacion_manual_cliente_solo_cancela_deudas_completas \
  pos.tests.SaldosInicialesPosTests.test_conciliacion_manual_proveedor_solo_cancela_deudas_completas
```

Resultado:

- `OK`

Tambien se ejecuto esta validacion ampliada:

```powershell
.\venv\Scripts\python.exe manage.py test \
  pos.tests.SaldosInicialesPosTests
```

Resultado:

- `OK`

Tambien se verifico que no quedaron errores de analisis en:

- `pos/views.py`
- `pos/urls.py`
- `pos/templates/pos/terminal.html`
- `pos/printing.py`
- `pos/tests.py`

## Alcance no modificado

No se cambio en esta pasada:

- la estructura del resumen impreso
- la logica manual de cobro de deuda cuando el usuario selecciona deudas y completa el faltante con un medio de pago

Eso significa que el ticket ya diferencia deuda original y saldo pendiente, pero no se rediseño el resumen general ni el resto de los comprobantes.

## Documento de soporte

El analisis funcional y tecnico previo sigue documentado en:

- `docs/README_ANALISIS_ADELANTOS_AUTOMATICOS.md`