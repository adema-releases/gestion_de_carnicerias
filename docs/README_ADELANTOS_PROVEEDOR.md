# Implementacion: adelantos de proveedores y saldo a favor

Este documento describe el flujo de adelantos parciales a proveedores, replicando el criterio ya probado en clientes.

## Objetivo

Permitir registrar dinero pagado por adelantado a un proveedor como saldo a favor y aplicarlo despues al cancelar deudas de cuenta corriente.

La regla central es separar dos hechos:

1. Cuando se registra el adelanto al proveedor, sale dinero real de caja por un medio de pago.
2. Cuando ese adelanto se usa para cancelar deuda, no sale dinero nuevo; solo se consume saldo a favor.

Esto evita duplicar egresos y mantiene trazabilidad completa en POS, Excel, admin y tesoreria.

## Archivos principales

- `compras/models.py`: modelos `AdelantoProveedor` y `CancelacionDeudaProveedorAdelantoDetalle`; `CancelacionDeudaProveedor` separa `total`, `monto_pagado` y `monto_adelanto_aplicado`.
- `compras/migrations/0010_adelantos_proveedor.py`: crea las tablas nuevas y migra cancelaciones historicas con `monto_pagado = total`.
- `tesoreria/models.py`: agrega el tipo `adelanto_proveedor`.
- `tesoreria/signals.py`: los adelantos de proveedor generan egreso real; las cancelaciones solo generan egreso por `monto_pagado`.
- `pos/views.py`: agrega APIs, cuenta corriente, Excel, cierre de caja, operaciones y validaciones.
- `pos/urls.py`: agrega endpoints de adelanto y cuenta corriente de proveedor.
- `pos/templates/pos/terminal.html`: agrega modal de adelanto, resumen de adelantos al pagar deudas y panel CC de proveedores.
- `compras/admin.py`: administra adelantos, aplicaciones y saldo neto.
- `gestion_de_carnicerias/admin_override.py`: actualiza PDF de estado de cuenta y balances administrativos.
- `pos/tests.py`: cubre registro, aplicacion parcial, aplicacion total y pago insuficiente.

## Flujo POS

### Registrar adelanto

Desde el POS se puede abrir `Adelanto proveedor`.

El cajero carga:

- proveedor;
- importe;
- medio de pago real;
- descripcion opcional.

Validaciones:

- requiere caja abierta;
- requiere permiso `puede_registrar_adelanto_proveedor`;
- requiere cuenta corriente habilitada para el usuario;
- no permite usar `Cuenta Corriente` como medio del adelanto;
- el importe debe ser mayor a cero.

Resultado:

- se crea `AdelantoProveedor`;
- se crea `MovimientoCuenta` de tipo `adelanto_proveedor` como egreso;
- el saldo queda disponible para aplicar a deudas del proveedor.

### Pagar deudas con adelanto

Al cargar deudas del proveedor, el POS trae tambien el adelanto disponible.

Al seleccionar deudas, muestra:

- adelanto disponible;
- adelanto que se aplicara;
- faltante a pagar;
- importe pagado;
- diferencia.

La operacion solo se confirma si las deudas seleccionadas quedan canceladas por completo:

```text
adelantos_aplicados + importe_pagado >= total_a_cancelar
```

Si el adelanto cubre todo, no se exige medio de pago y no se genera egreso nuevo.

Si cubre una parte, se exige medio real solo para el faltante.

Si el importe pagado supera el faltante, el sistema informa la diferencia y registra como `monto_pagado` solo lo necesario para cancelar la deuda. Para dejar dinero adicional a favor debe usarse el modal `Adelanto proveedor`.

## Cuenta corriente de proveedor

El modal operativo de proveedores muestra solo:

- deudas pendientes;
- adelantos disponibles;
- pendiente CC;
- adelanto disponible;
- saldo operativo.

El historial completo queda en `Exportar Excel` y en el PDF de estado de cuenta del admin.

## Excel

El Excel de proveedor incluye:

- `Resumen`;
- `Deudas`;
- `Pagos`;
- `Adelantos`;
- `Movimientos`.

La hoja `Pagos` diferencia `Total aplicado`, `Pagado directo` y `Adelanto aplicado` para no confundir aplicacion contable con salida real de caja.

## Validaciones ejecutadas

```bash
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py migrate
python manage.py test pos.tests
```

Resultado actual:

- sin migraciones pendientes;
- system check sin issues;
- migraciones `compras.0010_adelantos_proveedor` y `tesoreria.0004_alter_movimientocuenta_tipo` aplicadas;
- `pos.tests`: 37 tests OK.