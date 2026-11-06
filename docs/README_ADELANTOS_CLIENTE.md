# Implementacion: adelantos de clientes y saldo a favor

Este documento describe el flujo final implementado para clientes. Queda como referencia para replicar el mismo criterio en proveedores.

## Objetivo

Se agrego la posibilidad de registrar dinero entregado por un cliente como `saldo a favor` y aplicarlo despues al cancelar deudas de cuenta corriente.

La regla central es separar dos hechos contables distintos:

1. Cuando el cliente deja un adelanto, entra dinero real a caja por un medio de pago.
2. Cuando ese adelanto se usa para cancelar deuda, no entra dinero nuevo; solo se consume saldo a favor.

Esto evita duplicar ingresos, conserva la trazabilidad y permite que el POS trabaje de forma mas intuitiva: el cajero ve que falta cobrar hoy, no todo el historial contable.

## Archivos modificados

- `ventas/models.py`: nuevos modelos `AdelantoCliente` y `CobroDeudaAdelantoDetalle`; `CobroDeuda` separa `total`, `monto_recibido` y `monto_adelanto_aplicado`.
- `ventas/migrations/0011_adelantos_cliente.py`: crea tablas nuevas y migra cobros historicos con `monto_recibido = total`.
- `ventas/admin.py`: administra adelantos, aplicaciones y saldo neto del cliente.
- `tesoreria/models.py`: agrega el tipo de movimiento `adelanto_cliente`.
- `tesoreria/migrations/0003_alter_movimientocuenta_tipo.py`: migra el nuevo tipo de movimiento.
- `tesoreria/signals.py`: los adelantos generan ingreso real; los cobros de deuda solo generan ingreso por dinero nuevo recibido.
- `pos/views.py`: agrega APIs, calculos de cuenta corriente, Excel, cierre de caja, operaciones, conciliacion por medios y validaciones de cobro completo.
- `pos/urls.py`: agrega `/pos/api/clientes/adelanto/`.
- `pos/templates/pos/terminal.html`: agrega modal de adelanto, mejora cobro de deudas, agrega importe pagado/vuelto y simplifica el modal de cuenta corriente.
- `pos/printing.py`: tickets termicos para adelantos y cobros con desglose.
- `gestion_de_carnicerias/admin_override.py`: PDF de estado de cuenta con adelantos, aplicaciones y saldo neto.
- `pos/tests.py`: pruebas del flujo completo.

## Modelo de datos

### `AdelantoCliente`

Representa dinero real que el cliente dejo a favor.

Campos principales:

- `cliente`: cliente asociado.
- `fecha`: momento del registro.
- `monto`: importe recibido como adelanto.
- `medio_de_pago`: medio real usado para recibir el dinero.
- `turno`: caja abierta donde se registro.
- `usuario`: cajero que lo registro.
- `descripcion`: detalle opcional.

Propiedades:

- `monto_aplicado`: suma de lo ya consumido en cobros de deuda.
- `saldo_disponible`: remanente disponible para futuras cancelaciones.

### `CobroDeudaAdelantoDetalle`

Relaciona un cobro de deuda con uno o mas adelantos consumidos.

Permite saber:

- que adelanto se uso;
- cuanto se uso;
- en que cobro se consumio;
- que ventas o saldos iniciales quedaron cancelados con ese cobro.

### Cambios en `CobroDeuda`

`CobroDeuda` ahora distingue tres conceptos:

- `total`: total aplicado a las deudas seleccionadas. Es lo que queda cancelado.
- `monto_recibido`: dinero nuevo recibido en ese momento. Es lo que impacta caja/tesoreria.
- `monto_adelanto_aplicado`: saldo a favor usado para cubrir parte o todo el total.

Los cobros historicos quedan compatibles porque la migracion copia `total` a `monto_recibido`.

## Flujo POS

### 1. Registrar adelanto

Desde el POS se puede abrir el modal `Adelanto cliente`.

El cajero carga:

- cliente;
- importe;
- medio de pago real;
- descripcion opcional.

Validaciones:

- requiere caja abierta;
- requiere permiso de cobro de deuda de cliente;
- no permite usar `Cuenta Corriente` como medio del adelanto;
- el importe debe ser mayor a cero;
- si el medio es efectivo, se intenta abrir el cajon como en otros ingresos.

Resultado:

- se crea `AdelantoCliente`;
- se crea `MovimientoCuenta` de tipo `adelanto_cliente`;
- el saldo queda disponible para ese cliente;
- el dinero entra a caja en el momento del adelanto.

### 2. Cobrar deudas con saldo a favor

En el modal `Cobro de Deudas`, al cargar un cliente, el POS trae sus deudas pendientes y su saldo a favor disponible.

Al seleccionar deudas, el modal muestra:

- `Saldo a favor disponible`;
- `Se aplicara desde adelantos`;
- `Faltante a cobrar`;
- `Medio de pago del importe pagado`;
- `Importe pagado`;
- resumen con `Total a cancelar`, `Adelantos aplicados`, `Resta pagar`, `Importe pagado` y `Vuelto` o `Faltante`.

Regla operativa importante: las deudas seleccionadas solo se pueden confirmar si quedan canceladas por completo.

Es decir:

```text
adelantos_aplicados + importe_pagado >= total_a_cancelar
```

Si no alcanza, el POS no registra el cobro.

### 3. Vuelto y dinero real recibido

El cajero puede ingresar un importe mayor al faltante.

Ejemplo:

- deuda seleccionada: $50.000;
- adelanto disponible aplicado: $3.000;
- resta pagar: $47.000;
- cliente entrega: $50.000.

Resultado:

- `total = 50000`: se cancela toda la deuda;
- `monto_adelanto_aplicado = 3000`: se consume saldo a favor;
- `monto_recibido = 47000`: solo esto entra como cobro real;
- `vuelto = 3000`: se informa al cajero, pero no infla caja ni tesoreria.

### 4. Adelanto cubre toda la deuda

Si el saldo a favor alcanza para cubrir todo:

- no se exige medio de pago;
- `monto_recibido = 0`;
- `monto_adelanto_aplicado = total`;
- no se genera ingreso nuevo en tesoreria;
- solo se consume saldo a favor.

### 5. Adelanto cubre solo una parte

Si el saldo a favor cubre una parte:

- se exige medio de pago para lo que resta;
- `monto_recibido` queda por el faltante real;
- `monto_adelanto_aplicado` queda por el saldo consumido;
- tesoreria solo registra el dinero nuevo recibido.

### 6. No hay adelanto disponible

Si no hay saldo a favor:

- el total seleccionado debe cubrirse con `Importe pagado`;
- se exige medio de pago;
- `monto_recibido = total` salvo que el cliente entregue de mas, en cuyo caso el extra queda como vuelto.

## Modal de cuenta corriente del cliente

El modal de cuenta corriente del POS fue simplificado para uso operativo diario.

En pantalla solo muestra:

- cuentas corrientes pendientes;
- adelantos disponibles;
- `Pendiente CC`;
- `Adelanto disponible`;
- `Saldo operativo`.

No muestra pagos historicos, adelantos ya consumidos ni movimientos cronologicos. Esa informacion queda en Excel y PDF.

### Criterio de visualizacion

Si una venta o saldo inicial ya fue cancelado, deja de aparecer en el modal.

Ejemplo Juan:

- Juan tenia una deuda de $50.000.
- Se aplicaron $3.000 de adelanto.
- Se recibieron $47.000 por caja.
- La deuda quedo cancelada.

En el modal operativo, Juan queda en cero:

- `Pendiente CC = $0`;
- `Adelanto disponible = $0`;
- `Saldo operativo = $0`;
- sin deudas pendientes;
- sin adelantos disponibles.

El historial de como se llego a cero se consulta exportando Excel o desde el PDF de estado de cuenta.

### Scroll de modales

Los modales del POS tienen altura maxima relativa a la pantalla y scroll interno cuando el contenido excede el viewport. Esto evita que botones o secciones queden fuera de pantalla.

## Excel de cuenta corriente

El Excel mantiene el historial completo aunque el modal sea compacto.

Se genera desde `Exportar Excel` en el panel de cuenta corriente del cliente.

Hojas incluidas:

### `Resumen`

Incluye:

- fecha/hora de emision;
- cliente;
- telefono;
- total fiado;
- cobrado directo;
- adelantos registrados;
- adelantos aplicados;
- saldo a favor disponible;
- saldo neto;
- cantidad de movimientos de deuda;
- cantidad de pagos.

### `Ventas Fiado`

Columnas:

- `Fecha`;
- `Origen`;
- `ID venta`;
- `Ticket`;
- `Descripcion`;
- `Categoria`;
- `Importe fiado`;
- `Pagado`;
- `Saldo`.

Incluye ventas fiadas y saldos iniciales, tanto pendientes como cancelados, para conservar historial.

### `Pagos`

Columnas:

- `Fecha`;
- `Medio de pago`;
- `Descripcion`;
- `Total aplicado`;
- `Cobrado directo`;
- `Adelanto aplicado`;
- `Aplicacion`.

Esta separacion es clave:

- `Total aplicado`: deuda cancelada por ese cobro.
- `Cobrado directo`: dinero nuevo recibido.
- `Adelanto aplicado`: saldo a favor consumido.
- `Aplicacion`: detalle de ventas/saldos y adelantos usados.

### `Adelantos`

Columnas:

- `Fecha`;
- `Medio de pago`;
- `Descripcion`;
- `Monto`;
- `Aplicado`;
- `Disponible`;
- `Aplicaciones`.

Permite ver que adelanto entro, cuanto queda disponible y en que cobro/deuda se uso.

### `Movimientos`

Columnas:

- `Fecha`;
- `Tipo`;
- `Descripcion`;
- `Debe`;
- `Haber`;
- `Saldo`.

Es la vista cronologica completa de la cuenta corriente.

## PDF de estado de cuenta

El PDF de cliente incluye una seccion `Adelantos / saldo a favor` con:

- fecha del adelanto;
- descripcion;
- medio de pago;
- monto recibido;
- monto aplicado;
- disponible;
- detalle resumido de donde se uso.

El resumen final diferencia:

- total fiado;
- total aplicado a deudas;
- cobrado directo;
- adelantos registrados;
- adelantos aplicados;
- saldo a favor disponible;
- saldo neto de cuenta corriente.

## Caja, cierre y tesoreria

Reglas contables implementadas:

- Un adelanto suma a caja cuando se registra.
- Un cobro de deuda suma a caja solo por `monto_recibido`.
- La aplicacion de adelanto contra deuda no suma a caja.
- El vuelto informado no suma a caja ni a tesoreria.
- Las cards por medio de pago incluyen adelantos como ingresos reales.
- El PDF de cierre incluye `Ingresos (adelantos cliente)`.
- La conciliacion por medios incluye adelantos en el medio real usado.

## Tickets

Los tickets POS reconocen:

- `ADELANTO DE CLIENTE`;
- cobros de deuda con desglose de `Recibido` y `Saldo a favor`;
- adelantos aplicados dentro del detalle del cobro.

## Endpoints

### `POST /pos/api/clientes/adelanto/`

Payload:

```json
{
  "cliente_id": 1,
  "monto": "50000",
  "medio_id": 2,
  "descripcion": "Adelanto para compras futuras"
}
```

Respuesta:

```json
{
  "ok": true,
  "id": 10,
  "monto": 50000.0,
  "saldo_disponible": 50000.0
}
```

### `GET /pos/api/clientes/deudas/?cliente_id=...`

Devuelve deudas pendientes y saldo a favor disponible:

```json
{
  "ok": true,
  "adelanto_disponible": 2500.0,
  "deudas": []
}
```

### `POST /pos/api/cobro-deuda/`

Payload:

```json
{
  "cliente_id": 1,
  "medio_id": 2,
  "venta_ids": [15, "saldo:3"],
  "importe_pagado": "50000",
  "descripcion": "Cancela deuda"
}
```

`medio_id` puede omitirse si el adelanto cubre todo.

Respuesta:

```json
{
  "ok": true,
  "id": 22,
  "total": 50000.0,
  "monto_recibido": 47000.0,
  "monto_adelanto_aplicado": 3000.0,
  "importe_pagado": 50000.0,
  "vuelto": 3000.0
}
```

Validaciones del endpoint:

- requiere cliente;
- requiere al menos una deuda;
- valida que las deudas pertenezcan al cliente;
- ignora deudas sin saldo pendiente;
- rechaza medio `Cuenta Corriente`;
- exige medio si hay dinero nuevo recibido;
- rechaza `importe_pagado` negativo o invalido;
- rechaza cobros donde `importe_pagado` no cubre el faltante;
- registra como `monto_recibido` solo lo necesario para cancelar, no el importe entregado de mas.

## Casos cubiertos

### Caso A: adelanto antes de vender

1. Cliente deja $50.000.
2. Se registra adelanto con efectivo, transferencia u otro medio real.
3. El cliente queda con saldo a favor.
4. Luego se hacen ventas fiadas.
5. Al cobrar deudas, el sistema usa el saldo a favor primero.

### Caso B: deuda con adelanto parcial

1. Cliente debe $10.000.
2. Tiene $2.500 de adelanto disponible.
3. El POS aplica $2.500.
4. Resta pagar $7.500.
5. Se registra cobro directo por $7.500.
6. La deuda queda cancelada.

### Caso C: adelanto cubre todo

1. Cliente debe $10.000.
2. Tiene $50.000 de saldo a favor.
3. El POS aplica $10.000.
4. No solicita medio de pago.
5. Quedan $40.000 disponibles.

### Caso D: cliente paga de mas

1. Cliente debe $50.000.
2. Tiene $3.000 de adelanto.
3. Resta pagar $47.000.
4. El cliente entrega $50.000.
5. El POS informa vuelto $3.000.
6. Caja registra solo $47.000 como cobro de deuda.

### Caso E: cliente paga de menos

1. Cliente debe $50.000.
2. Tiene $3.000 de adelanto.
3. Resta pagar $47.000.
4. El cliente entrega $45.000.
5. El POS bloquea la operacion porque las deudas seleccionadas no quedarian canceladas por completo.

## Validaciones ejecutadas

Comandos ejecutados durante la implementacion:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py test pos.tests
```

Resultados actuales:

- `makemigrations --check --dry-run`: sin cambios pendientes cuando se ejecuto despues de las migraciones manuales.
- `python manage.py migrate`: aplicadas `tesoreria.0003_alter_movimientocuenta_tipo` y `ventas.0011_adelantos_cliente`.
- `python manage.py check`: sin issues.
- `python manage.py test pos.tests`: 26 tests OK.

## Tests agregados o ajustados

Se cubrio:

- registrar adelanto desde POS;
- rechazar adelantos con medio `Cuenta Corriente`;
- generar movimiento de tesoreria al registrar adelanto;
- aplicar adelanto parcial y cobrar solo el faltante;
- aplicar adelanto total sin exigir medio de pago;
- conservar remanente de saldo a favor;
- rechazar cobros donde el importe pagado no cancela por completo las deudas seleccionadas;
- informar vuelto sin inflar `monto_recibido` cuando el cliente paga de mas;
- reflejar adelantos en la cuenta corriente del cliente;
- mantener el Excel con hojas `Resumen`, `Ventas Fiado`, `Pagos`, `Adelantos` y `Movimientos`;
- validar nombres administrativos de los nuevos modelos.

## Guia para replicar en proveedores

Para proveedores conviene replicar el mismo patron, invirtiendo el sentido operativo segun corresponda.

Puntos a mantener iguales:

- separar dinero real de aplicacion contable;
- crear un modelo equivalente a `AdelantoCliente` para saldos a favor del proveedor, si el negocio lo requiere;
- crear una tabla detalle equivalente para saber que saldo se aplico a que cancelacion;
- no duplicar movimientos de tesoreria cuando se consume saldo ya registrado;
- mostrar en el modal operativo solo lo pendiente y lo disponible;
- dejar el historial completo en Excel/PDF;
- validar que las deudas seleccionadas queden canceladas por completo antes de confirmar;
- permitir importe pagado mayor al faltante e informar la diferencia sin inflar caja;
- agregar tests de adelanto parcial, adelanto total, pago insuficiente, pago con diferencia y exportacion.

Decision importante para proveedores:

- Si el proveedor nos deja saldo a favor, el registro inicial probablemente no sea un ingreso sino una condicion contable o un egreso compensado, segun el flujo real del negocio.
- Si nosotros pagamos de mas a un proveedor, debe definirse si ese exceso queda como saldo a favor para futuras compras o si se maneja como vuelto/diferencia.
- Antes de implementar proveedores, hay que fijar exactamente cuando entra o sale dinero real de caja para no duplicar egresos.

## Consideraciones finales

- El modal POS es operativo y compacto.
- El Excel y el PDF son las vistas historicas/auditables.
- `total` significa deuda cancelada.
- `monto_recibido` significa dinero nuevo recibido.
- `monto_adelanto_aplicado` significa saldo a favor consumido.
- `importe_pagado` es lo que el cajero ingreso en pantalla para validar cobro/vuelto.
- `vuelto` se informa al usuario, pero no debe impactar caja como ingreso.
- El saldo neto puede ser negativo; eso significa saldo a favor del cliente.
- El flujo de proveedores aun no fue modificado.