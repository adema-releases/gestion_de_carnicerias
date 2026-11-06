# Tutoriales Operativos - Gestion de Carnicerias

Esta guia explica como usar Gestion de Carnicerias en el dia a dia y como administrarlo. Esta escrita para negocios que necesitan registrar movimientos de dinero de forma simple: ventas, gastos, compras/pagos a proveedores, retiros, cobros, deudas y cierres de caja.

El sistema sirve especialmente para locales que quieren control interno. Por ejemplo: un negocio con dos locales donde cada local registra ventas, gastos y compras, pero no necesita llevar stock articulo por articulo. En ese caso, Gestion de Carnicerias funciona como una caja diaria, un registro de cuentas corrientes y una herramienta de conciliacion.

## 1. Conceptos basicos

Antes de operar conviene entender estas palabras:

| Concepto | Que significa |
| --- | --- |
| POS | Pantalla diaria donde opera el cajero: ventas, gastos, retiros, cobros y cierre. |
| Turno o caja | Jornada abierta por un usuario para registrar movimientos. |
| Saldo inicial | Efectivo declarado al abrir la caja. |
| Saldo final | Efectivo contado y declarado al cerrar la caja. |
| Medio de pago | Forma de pago: efectivo, Mercado Pago, fiado, tarjeta, transferencia, etc. |
| Cuenta corriente | Deuda. En ventas es deuda del cliente; en proveedor es deuda con proveedor. |
| Ledger | Libro interno de movimientos reales de dinero (`MovimientoCuenta`). |
| Superadmin | Usuario con acceso total al admin y permisos POS completos. |
| Cajero | Usuario operativo que usa el POS con permisos limitados. |

## 2. Primer inicio del sistema

Desde la carpeta del proyecto:

```powershell
python manage.py init_system
```

Este comando aplica migraciones y crea datos iniciales.

Usuarios iniciales:

| Rol | Usuario | Clave |
| --- | --- | --- |
| Superadmin | `ADEMASISTEMAS` | `Adema123` |
| Cajero | `cajero1` | `Cajero1234` |
| Cajero | `cajero2` | `Cajero1234` |

Medios iniciales:

- `Efectivo`
- `Mercado Pago`
- `Fiado` como `Cuenta Corriente`

Categorias de gasto iniciales:

- `Luz`
- `Alquiler`
- `Sueldos`
- `Gastos Generales`

URLs principales:

| URL | Uso |
| --- | --- |
| `/pos/` | Terminal de caja diaria. |
| `/admin/` | Administracion, reportes y configuracion. |
| `/accounts/login/` | Login. |

Recomendacion inmediata: cambiar las claves iniciales antes de usar datos reales.

## 3. Roles del sistema

### Superadmin

El superadmin administra todo el sistema.

Puede:

- Entrar a `/admin/`.
- Crear usuarios.
- Cambiar contrasenas.
- Configurar permisos de cajeros.
- Asignar medios de pago a cajeros.
- Crear medios de pago.
- Crear categorias.
- Consultar ventas, gastos, proveedores, clientes y turnos.
- Descargar reportes Excel/PDF.
- Descargar PDFs de cierre de caja.
- Ver estados de cuenta de clientes y proveedores.
- Operar en `/pos/` si abre su propia caja.

Aunque sea superadmin, para registrar operaciones desde POS debe abrir turno igual que cualquier cajero.

### Cajero

El cajero usa principalmente `/pos/`.

Puede hacer solo lo que tenga habilitado en `PermisosCajero`:

- Abrir/cerrar caja.
- Registrar ventas.
- Registrar gastos.
- Registrar pagos o deudas a proveedor.
- Registrar retiros.
- Cobrar deudas de clientes.
- Crear/editar clientes.
- Crear/editar proveedores.
- Crear categorias de venta.

Ademas, solo puede usar los medios de pago asignados.

## 4. Permisos de cajero

Los permisos estan en el admin, modelo `Cashier permissions` o `PermisosCajero`.

| Permiso | Que habilita en POS |
| --- | --- |
| `puede_registrar_venta` | Boton y API de venta. |
| `puede_registrar_gasto` | Boton y API de gasto. |
| `puede_pagar_proveedor` | Pago/deuda proveedor y pago de cuenta proveedor. |
| `puede_registrar_retiro` | Retiro de efectivo. |
| `puede_cobrar_deuda_cliente` | Cobro de deuda de cliente. |
| `puede_crear_editar_cliente` | Crear/editar clientes desde POS. |
| `puede_crear_editar_proveedor` | Crear/editar proveedores desde POS. |
| `puede_crear_categoria_venta` | Crear categorias de venta desde POS. |
| `puede_abrir_cerrar_caja` | Abrir y cerrar caja. |

Los cajeros creados por `init_system` pueden operar caja, ventas, gastos, retiros, proveedores y cobros, pero no pueden crear/editar clientes, proveedores ni categorias desde POS.

## 5. Como configurar permisos

1. Entrar a `/admin/` con el superadmin.
2. Buscar `Cashier permissions`.
3. Abrir el registro del usuario.
4. Marcar o desmarcar permisos.
5. Guardar.

Tambien se pueden editar desde el admin de usuarios porque `PermisosCajero` aparece como inline dentro del usuario.

Recomendacion practica:

- Cajero comun: ventas, gastos, retiros, cobros y abrir/cerrar caja.
- Encargado: lo anterior + crear/editar clientes/proveedores/categorias.
- Administrador: usar superadmin o staff con permisos de admin cuidadosamente configurados.

## 6. Como dar de alta un nuevo usuario cajero

1. Entrar a `/admin/` con superadmin.
2. Ir a `Users` si esta visible o acceder al modulo de usuarios de Django.
3. Crear un usuario nuevo.
4. Definir `username` y password.
5. Completar nombre y apellido si se desea.
6. Dejar `is_staff=False` para que no entre al admin.
7. Dejar `is_superuser=False`.
8. Guardar.

Al guardar, el sistema crea automaticamente:

- `UserProfile`
- `PermisosCajero`

Luego hay que revisar permisos y medios de pago.

## 7. Como crear un usuario administrador

1. Entrar a `/admin/` con superadmin.
2. Crear un usuario.
3. Marcar `is_staff=True` si debe entrar al admin.
4. Marcar `is_superuser=True` solo si debe tener control total.
5. Guardar.

Recomendacion: usar pocos superusuarios. Para usuarios administrativos parciales, conviene usar `is_staff=True` y permisos Django especificos, si se decide administrar permisos a nivel admin.

## 8. Como asignar medios de pago a un cajero

1. Entrar a `/admin/`.
2. Ir a `Cashier payment method assignments` o `AsignacionMedioPagoCajero`.
3. Crear una asignacion.
4. Elegir usuario.
5. Elegir medio de pago.
6. Dejar `activo=True`.
7. Guardar.

Para revocar un medio:

1. Abrir la asignacion.
2. Desmarcar `activo`.
3. Guardar.

Regla importante:

- Si un cajero no tiene ninguna asignacion, ve todos los medios.
- Si tiene al menos una asignacion, ve solo las activas.

Por eso, si se quiere controlar estrictamente que medios usa cada cajero, hay que cargar sus asignaciones.

## 9. Como crear medios de pago

1. Entrar a `/admin/`.
2. Ir a `Payment methods` o `MedioDePago`.
3. Crear nuevo medio.
4. Completar `nombre`.
5. Elegir `categoria`.
6. Guardar.

Ejemplos:

| Nombre | Categoria |
| --- | --- |
| Efectivo | Efectivo |
| Mercado Pago | Transferencia Bancaria |
| Visa Credito | Tarjeta de Crédito |
| Debito Bancario | Tarjeta de Débito |
| Fiado | Cuenta Corriente |
| Transferencia Banco Galicia | Transferencia Bancaria |

La categoria es importante porque define reglas. Por ejemplo, `Cuenta Corriente` se interpreta como deuda y no como movimiento real de dinero.

## 10. Configuracion del negocio

1. Entrar a `/admin/`.
2. Ir a `Configuration` o `Configuracion`.
3. Completar datos del negocio:
   - nombre
   - direccion
   - telefono
   - WhatsApp
   - Instagram
   - Facebook
   - sitio web
   - descripcion
4. Guardar.

Estos datos se usan, entre otras cosas, en la terminal POS y en tickets imprimibles.

## 11. Categorias de venta

Las categorias de venta sirven para clasificar ingresos: por ejemplo `Mostrador`, `Delivery`, `Bebidas`, `Comida`, `Servicios`, `Local 1`, `Local 2`.

Para crearlas desde admin:

1. Entrar a `/admin/`.
2. Ir a `Categories` o `Categoria`.
3. Crear categoria.
4. Guardar.

Para crearlas desde POS:

1. El cajero debe tener `puede_crear_categoria_venta=True`.
2. Abrir modal `Venta`.
3. En el panel de categorias, usar `Nueva cat.`.
4. Escribir el nombre.
5. Guardar.

Nota: si no hay categorias cargadas, el modal de venta oculta la columna de categorias.

## 12. Categorias de gasto

Las categorias de gasto clasifican egresos: luz, alquiler, sueldos, compras internas, movilidad, limpieza, etc.

Para crearlas:

1. Entrar a `/admin/`.
2. Ir a `Expense categories` o `CategoriaGasto`.
3. Crear categoria.
4. Guardar.

El POS las muestra en el modal `Gasto`.

## 13. Operacion diaria del cajero

### Paso 1: entrar al POS

1. Ir a `/pos/`.
2. Iniciar sesion con usuario y clave.
3. Si la caja esta cerrada, el sistema muestra un aviso.

### Paso 2: abrir caja

1. Presionar `Abrir Caja`.
2. Ingresar `Saldo inicial en efectivo`.
3. Confirmar con `Abrir`.

El saldo inicial representa el efectivo fisico con el que empieza el turno. Si no hay efectivo inicial, se puede ingresar `0`.

Al abrir caja se crea un `TurnoCaja`. Si el saldo inicial es mayor a cero, se crea tambien un movimiento de apertura en efectivo.

### Paso 3: operar

Con caja abierta aparecen los botones de operacion habilitados por permisos:

- `Venta`
- `Gasto`
- `Proveedor`
- `Retiro`
- `Cobro Deuda`
- `Pagar Cuenta Prov.`

Tambien se muestran:

- Operaciones del turno.
- Ingresos y egresos.
- Saldo efectivo esperado.
- Tarjetas por medio de pago.

### Paso 4: cerrar caja

1. Presionar `Cerrar caja`.
2. Revisar resumen de ingresos, egresos y conciliacion por medios.
3. Contar el efectivo fisico.
4. Ingresar `Saldo final en efectivo`.
5. Confirmar cierre.
6. El sistema abre/descarga el PDF de cierre.

## 14. Registrar una venta simple

Uso tipico: una venta pagada completamente con efectivo, Mercado Pago, tarjeta o transferencia.

1. Abrir caja.
2. Presionar `Venta`.
3. Ingresar `Importe Total`.
4. Elegir categoria si existen categorias cargadas.
5. Elegir cliente si corresponde; si no, dejar `Consumidor final`.
6. Agregar descripcion opcional.
7. Seleccionar medio de pago.
8. Ingresar importe pagado por ese medio.
9. Presionar `+ Agregar`.
10. Verificar que el pendiente quede en `$0`.
11. Presionar `Emitir Ticket`.

Resultado:

- Se crea una `Venta`.
- Se crea un ticket numerado dentro del turno.
- Se genera movimiento de ingreso si el medio no es cuenta corriente.
- Se abre el ticket imprimible.

## 15. Registrar una venta con varios medios de pago

Ejemplo: venta de $10.000, paga $6.000 en efectivo y $4.000 por Mercado Pago.

1. Presionar `Venta`.
2. Ingresar importe total: `10000`.
3. Seleccionar `Efectivo`.
4. Ingresar `6000` y presionar `+ Agregar`.
5. Seleccionar `Mercado Pago`.
6. Ingresar `4000` y presionar `+ Agregar`.
7. Confirmar que el pendiente sea `$0`.
8. Emitir ticket.

Resultado:

- Se crea una `Venta` por el total.
- Se crean dos `VentaPago`.
- El sistema toma como medio principal el de mayor importe.
- El ledger genera un movimiento por cada medio no corriente.

Si el pago supera el total y hay efectivo, el POS muestra vuelto.

## 16. Registrar una venta fiada o en cuenta corriente

Uso tipico: el cliente se lleva productos/servicios y queda debiendo.

1. Abrir `Venta`.
2. Ingresar importe total.
3. Seleccionar un cliente. Esto es obligatorio para cuenta corriente.
4. Seleccionar medio `Fiado` o el medio cuya categoria sea `Cuenta Corriente`.
5. Agregar el importe.
6. Emitir ticket.

Resultado:

- Se crea una venta asociada al cliente.
- Queda saldo pendiente.
- No se genera ingreso real de caja hasta que el cliente pague la deuda.

Si no seleccionas cliente, el POS no permite usar cuenta corriente.

## 17. Crear o editar clientes desde POS

Esto depende del permiso `puede_crear_editar_cliente`.

Desde el modal de venta o cobro de deuda:

1. Presionar `Nuevo cliente`.
2. Ingresar nombre.
3. Ingresar telefono opcional.
4. Confirmar.

Para editar:

1. Seleccionar cliente.
2. Presionar `Editar cliente`.
3. Cambiar nombre y telefono.
4. Confirmar.

Si el cajero no tiene permiso, esos botones no aparecen.

## 18. Cobrar deuda de un cliente

Uso tipico: un cliente que tenia ventas fiadas viene a pagar.

1. Abrir caja.
2. Presionar `Cobro Deuda`.
3. Seleccionar cliente.
4. Presionar `Cargar deudas`.
5. Marcar una o varias deudas.
6. Elegir medio de pago para cancelar.
7. Escribir descripcion opcional.
8. Verificar total seleccionado.
9. Presionar `Registrar Cobro`.

Reglas:

- Solo aparecen ventas en cuenta corriente con saldo pendiente.
- No se puede cancelar deuda con medio `Cuenta Corriente`.
- El cobro genera ingreso real en el medio elegido.
- El sistema crea `CobroDeuda` y `CobroDeudaDetalle`.

Ejemplo:

```text
Cliente: Juan Perez
Deudas: Ticket #5 por $3.000 y Ticket #8 por $2.000
Medio de pago: Efectivo
Total cobrado: $5.000
```

Resultado:

- Las ventas quedan saldadas.
- El efectivo esperado aumenta $5.000.
- El ticket/comprobante de cobro puede imprimirse.

## 19. Registrar un gasto

Uso tipico: pagar luz, alquiler, limpieza, flete, sueldos, insumos menores.

1. Abrir caja.
2. Presionar `Gasto`.
3. Ingresar importe.
4. Escribir descripcion obligatoria.
5. Elegir categoria de gasto opcional.
6. Elegir medio de pago.
7. Presionar `Registrar`.

Reglas:

- El importe debe ser mayor a cero.
- La descripcion es obligatoria.
- No se puede registrar gasto con cuenta corriente.
- Genera egreso real en el medio elegido.

Ejemplos de descripcion:

- `Pago de luz local centro`
- `Limpieza semanal`
- `Compra de bolsas`
- `Flete mercaderia`

## 20. Registrar pago a proveedor

El boton `Proveedor` sirve para registrar pagos o deudas a proveedores.

### Pago real a proveedor

1. Presionar `Proveedor`.
2. Seleccionar proveedor.
3. Ingresar importe.
4. Elegir medio real: efectivo, transferencia, Mercado Pago, tarjeta, etc.
5. Escribir descripcion opcional, por ejemplo numero de factura.
6. Presionar `Registrar`.

Resultado:

- Se crea `PagoProveedor`.
- Se genera egreso real.
- Aparece en operaciones del turno como pago a proveedor.

### Deuda a proveedor en cuenta corriente

1. Presionar `Proveedor`.
2. Seleccionar proveedor.
3. Ingresar importe.
4. Elegir medio `Fiado` o categoria `Cuenta Corriente`.
5. Registrar.

Resultado:

- Se crea `PagoProveedor` como deuda pendiente.
- No se descuenta dinero de caja en ese momento.
- Luego puede cancelarse desde `Pagar Cuenta Prov.`.

Este flujo sirve para registrar compras a proveedor que todavia no fueron pagadas.

## 21. Crear o editar proveedores desde POS

Depende del permiso `puede_crear_editar_proveedor`.

Desde el modal `Proveedor` o `Pagar Cuenta Prov.`:

1. Presionar `Nuevo`.
2. Ingresar nombre del proveedor.
3. Ingresar telefono opcional.
4. Confirmar.

Para editar:

1. Seleccionar proveedor.
2. Presionar `Editar`.
3. Modificar datos.
4. Confirmar.

Si el cajero no tiene permiso, los botones no aparecen.

## 22. Pagar cuenta de proveedor

Uso tipico: pagar deudas anteriores registradas como cuenta corriente.

1. Abrir caja.
2. Presionar `Pagar Cuenta Prov.`.
3. Seleccionar proveedor.
4. Presionar `Cargar deudas`.
5. Marcar una o varias deudas.
6. Elegir medio de pago real.
7. Agregar descripcion opcional.
8. Presionar `Registrar Pago`.

Reglas:

- Solo aparecen `PagoProveedor` en cuenta corriente con saldo pendiente.
- No se puede cancelar con cuenta corriente.
- Se crea `CancelacionDeudaProveedor` y sus detalles.
- Genera egreso real en el medio elegido.

Ejemplo:

```text
Proveedor: Distribuidora Norte
Deudas: $12.000 + $8.000
Medio de pago: Transferencia
Total cancelado: $20.000
```

## 23. Registrar retiro de efectivo

Uso tipico: retirar efectivo para deposito, cambio, caja chica, entrega al dueno o traslado entre locales.

1. Abrir caja.
2. Presionar `Retiro`.
3. Ingresar importe.
4. Escribir descripcion opcional.
5. Presionar `Retirar`.

Resultado:

- Se crea `RetiroEfectivo`.
- Se genera egreso en efectivo.
- Baja el saldo efectivo esperado.

Ejemplos de descripcion:

- `Retiro encargado cierre manana`
- `Deposito banco`
- `Cambio para local 2`
- `Entrega a administracion`

## 24. Consultar operaciones del turno

En la pantalla principal del POS aparece `Operaciones del turno`.

Cada operacion muestra:

- Tipo.
- Descripcion.
- Hora.
- Importe positivo o negativo.
- Boton de detalle.

Tipos que pueden aparecer:

- `venta`
- `gasto`
- `proveedor`
- `deuda-proveedor`
- `pago-cuenta`
- `retiro`
- `cobro`

Al abrir detalle se pueden ver datos completos. Ventas, gastos y cobros pueden ser imprimibles segun el tipo de comprobante.

## 25. Entender las tarjetas de saldo por medio

El POS muestra tarjetas por cada medio permitido para el cajero.

Cada tarjeta muestra:

- Categoria del medio.
- Nombre del medio.
- Saldo neto.
- Ingresos.
- Egresos.

Interpretacion:

- En efectivo, el saldo incluye apertura, ventas/cobros en efectivo, gastos, retiros y pagos.
- En medios electronicos, el saldo muestra el neto operativo registrado para ese medio.
- Cuenta corriente puede representar deuda registrada, pero los movimientos reales dependen de cobros/cancelaciones con medios no corrientes.

## 26. Cerrar caja correctamente

El cierre es uno de los pasos mas importantes.

1. Presionar `Cerrar caja`.
2. Revisar el resumen:
   - ingresos del turno
   - egresos del turno
   - diferencia
   - ingresos en efectivo
   - egresos en efectivo
   - esperado en caja
   - conciliacion por medios
3. Contar el efectivo fisico real.
4. Ingresar ese monto en `Saldo final en efectivo`.
5. Confirmar.

El sistema calcula:

```text
Saldo efectivo esperado = saldo inicial + ingresos efectivo - egresos efectivo
Diferencia efectivo = saldo final declarado - saldo efectivo esperado
```

Si la diferencia es cero, el efectivo declarado coincide con lo esperado. Si hay diferencia positiva o negativa, conviene revisar ventas, gastos, retiros o cobros cargados durante el turno.

Al confirmar, se descarga o abre el PDF de cierre.

## 27. PDF de cierre

El PDF de cierre incluye:

- Numero de turno.
- Fecha.
- Usuario.
- Saldo inicial.
- Saldo final.
- Fecha/hora de cierre.
- Resumen de ventas, cobros, gastos, pagos, cancelaciones y retiros.
- Neto del turno.
- Saldo esperado en efectivo.
- Diferencia de efectivo declarado.
- Conciliacion por medios de pago.
- Listados de movimientos del turno.

Tambien se puede descargar desde admin, en `Register shifts` o `TurnoCaja`, usando el boton/accion de PDF.

## 28. Dashboard administrativo

El dashboard del admin permite analizar el negocio por rango de fechas y cajero.

Muestra:

- Ventas totales.
- Gastos.
- Cobros de deuda.
- Pagos a proveedores.
- Deuda cliente emitida.
- Deuda proveedor emitida.
- Saldo de clientes al inicio y al final.
- Saldo de proveedores al inicio y al final.
- Graficos por dia.
- Graficos por cajero.
- Ventas por medio de pago.
- Ventas por categoria.
- Balance estimado.

Exportaciones:

- Excel: `/admin/dashboard/export/excel/`
- PDF: `/admin/dashboard/export/pdf/`

El Excel incluye hojas de resumen, ventas, gastos, medios de pago y por cajero.

## 29. Estados de cuenta

### Cliente

Desde admin, en el listado de clientes, existe boton `PDF CC`.

Sirve para revisar:

- Ventas en cuenta corriente.
- Cobros aplicados.
- Saldo pendiente.

### Proveedor

Desde admin, en el listado de proveedores, existe boton `PDF CC`.

Sirve para revisar:

- Deudas registradas.
- Cancelaciones realizadas.
- Saldo pendiente.

## 30. Uso recomendado para dos locales

Si el negocio tiene dos locales y quiere registrar movimientos sin stock detallado, hay varias formas simples de organizarse.

### Opcion A: un cajero por local

Crear usuarios:

- `local1_caja`
- `local2_caja`

Ventajas:

- Los turnos quedan separados por usuario.
- El dashboard puede filtrar por cajero/local.
- Es facil saber que local registro cada venta/gasto.

### Opcion B: categorias por local

Crear categorias de venta:

- `Local 1`
- `Local 2`
- `Delivery Local 1`
- `Delivery Local 2`

Ventajas:

- Permite clasificar ventas dentro de un mismo usuario.

### Opcion C: descripcion estandar

Usar descripciones como:

- `Local centro - venta mostrador`
- `Local norte - gasto limpieza`

Ventajas:

- No requiere configurar muchas categorias.

Recomendacion: para control claro, usar un usuario por local y categorias simples para tipo de venta. Asi el dashboard por cajero funciona como filtro por local.

## 31. Buenas practicas de operacion

- Cada cajero debe usar su propio usuario.
- No compartir claves entre locales.
- Abrir caja al iniciar el dia o turno.
- Registrar gastos en el momento en que ocurren.
- Registrar retiros siempre que salga efectivo de caja.
- Usar cuenta corriente solo cuando realmente queda deuda.
- Cerrar caja al finalizar el turno.
- Revisar diferencias de efectivo antes de cerrar definitivamente.
- Descargar o guardar PDFs de cierre si el negocio los usa para control interno.
- Mantener clientes/proveedores activos o inactivos, evitando borrarlos si ya tienen movimientos.

## 32. Problemas frecuentes

### No puedo operar, aparece caja cerrada

Solucion:

1. Verificar si el usuario tiene permiso `puede_abrir_cerrar_caja`.
2. Abrir caja con saldo inicial.

### Aparece turno del dia anterior sin cerrar

Solucion:

1. Presionar `Cerrar turno anterior` si el permiso lo permite.
2. Ingresar saldo final real o estimado.
3. Cerrar.
4. Abrir nuevo turno del dia.

### No aparece un medio de pago

Posibles causas:

- El medio no existe en `MedioDePago`.
- El cajero tiene asignaciones y ese medio no esta asignado.
- La asignacion existe pero `activo=False`.

Solucion:

1. Entrar al admin.
2. Revisar `Payment methods`.
3. Revisar `Cashier payment method assignments`.
4. Activar/asignar el medio.

### No aparece cuenta corriente en venta

En el POS, la cuenta corriente se oculta si no hay cliente seleccionado. Primero selecciona cliente y luego elegi el medio `Fiado` o equivalente.

### No puedo cobrar deuda con Fiado

Es correcto. Una deuda no se cancela con otra deuda. Para cobrar deuda se debe usar efectivo, transferencia, Mercado Pago, tarjeta u otro medio real.

### No puedo registrar gasto con Fiado

Es correcto. Los gastos no pueden registrarse con cuenta corriente. Si se necesita registrar deuda con un tercero, usar el flujo de proveedor.

### El cierre muestra diferencia de efectivo

Revisar:

- Ventas en efectivo omitidas.
- Gastos cargados con medio incorrecto.
- Retiros no registrados.
- Cobros de deuda cargados como efectivo cuando fueron transferencia.
- Saldo inicial incorrecto.
- Error de conteo fisico.

### Un cliente/proveedor no aparece en POS

Revisar en admin si `activo=False`. El POS lista solo clientes y proveedores activos.

## 33. Seguridad basica

- Cambiar claves iniciales.
- Usar un usuario por persona o por caja/local.
- No dar `is_staff=True` a cajeros comunes.
- No compartir el superadmin para operacion diaria.
- Revisar permisos despues de crear usuarios.
- Limitar medios de pago por cajero cuando corresponda.
- Hacer backups frecuentes de `db.sqlite3` si se usa SQLite.

## 34. Backup recomendado con SQLite

Si el sistema usa SQLite, toda la informacion principal esta en `db.sqlite3`.

Recomendacion simple:

1. Cerrar la aplicacion o asegurarse de que nadie este escribiendo.
2. Copiar `db.sqlite3` a una carpeta de respaldo.
3. Incluir fecha y hora en el nombre.

Ejemplo:

```text
backups/db_2026-04-26_1800.sqlite3
```

Tambien conviene respaldar `media/` si se cargan logos u otros archivos.

## 35. Flujo recomendado de capacitacion

Para entrenar a un cajero nuevo:

1. Iniciar sesion con usuario de prueba.
2. Abrir caja con saldo inicial ficticio.
3. Registrar una venta en efectivo.
4. Registrar una venta multipago.
5. Crear una venta fiada con cliente.
6. Cobrar esa deuda.
7. Registrar un gasto.
8. Registrar una deuda a proveedor.
9. Cancelar esa deuda.
10. Registrar un retiro.
11. Revisar operaciones del turno.
12. Cerrar caja y descargar PDF.

Con esos pasos se cubren casi todos los movimientos que el sistema maneja.

## 36. Resumen final

Gestion de Carnicerias debe usarse como libro operativo diario de caja:

- Lo que entra se registra como venta o cobro.
- Lo que sale se registra como gasto, pago proveedor, cancelacion proveedor o retiro.
- Lo que queda pendiente se registra como cuenta corriente.
- Cada cajero/local trabaja con su turno.
- El cierre compara lo esperado contra lo declarado.
- El admin consolida reportes, saldos y exportaciones.

La filosofia del sistema es registrar movimientos claros y consultables, sin obligar al negocio a manejar stock detallado cuando su necesidad principal es control interno de dinero.