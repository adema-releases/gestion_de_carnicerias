# Plan de mejoras POS para proxima release

Este documento resume las mejoras pedidas para avanzar de a poco, con el menor riesgo posible, y deja claro que se tocaria para preparar el proximo build/release.

## Estado de implementacion

Implementado en esta tanda:

- la version instalada escucha en `0.0.0.0:8250` y acepta hosts de red local en modo desktop,
- se agregaron saldos iniciales auditables para clientes y proveedores,
- los saldos iniciales aparecen en el POS como deudas cobrables/pagables,
- los estados de cuenta PDF y saldos del admin contemplan esos saldos iniciales,
- cuando la opcion `Ocultar saldos de las cards` esta activa se oculta toda la seccion de cards,
- la lista de operaciones del POS tiene `Limpiar`, `Ocultar`/`Mostrar lista`, `Mostrar` historico y filtros dinamicos por tipo,
- se agregaron pruebas POS para cobro/pago de saldos iniciales,
- se aplicaron migraciones locales de `compras` y `ventas`.

Validado con:

- `python manage.py check`
- `python manage.py test pos.tests`
- `python manage.py migrate`

## Objetivo

Preparar una tanda de mejoras enfocada en:

- acceso al POS desde celular/tablet por QR en la version instalada,
- saldos iniciales para cuentas corrientes de clientes y proveedores,
- mejor aprovechamiento del espacio en POS cuando las cards de saldos estan ocultas,
- limpieza visual de la tabla/lista de movimientos del cajero sin borrar registros,
- filtros rapidos por tipo de movimiento dentro del POS.

La regla principal para esta tanda es no borrar ni alterar movimientos historicos: todo lo que sea "limpiar", "ocultar" o "filtrar" debe ser visual o de consulta, no destructivo.

---

## 1. Acceso desde celular por QR en la version instalada

### Pedido

Cuando el usuario abre el QR desde el POS instalado y entra desde un celular en la misma red, la app debe aceptar la peticion sin bloquear por host local.

### Estado anterior detectado

La app instalada se inicia desde `run_server.py` y levanta Django con:

- host: `127.0.0.1`,
- puerto: `8250`,
- `ALLOWED_HOSTS` por defecto: `127.0.0.1,localhost`.

El QR ya arma una URL con IP local desde `pos/views.py`, por ejemplo `http://192.168.x.x:8250`, pero el servidor instalado sigue escuchando solo en loopback. Eso hace que el telefono no pueda entrar correctamente aunque el QR sea correcto.

### Implementacion aplicada

En modo escritorio/instalado:

1. Cambiar el `runserver` para escuchar en `0.0.0.0:8250`.
2. Configurar `ALLOWED_HOSTS` para aceptar peticiones de red local en modo desktop.
3. Mantener el comportamiento actual para desarrollo normal si se ejecuta `manage.py runserver` manualmente.
4. Conservar el QR actual, porque ya detecta la IP local.

### Archivos a modificar

- `run_server.py`
- `gestion_de_carnicerias/settings.py`
- posiblemente `README_DJANGO_TO_WIN_APP.md` si queremos documentar el acceso desde otro dispositivo.

### Validaciones

- Abrir la app instalada en PC.
- Escanear QR desde celular conectado a la misma red WiFi.
- Confirmar login, carga del POS y operaciones GET/POST.
- Revisar si Windows Firewall pide permiso al primer inicio.

---

## 2. Saldo inicial en cuentas de clientes y proveedores

### Pedido

Agregar saldo inicial para clientes y proveedores, porque al instalar la app en un negocio real ya existen fiados/cuentas pendientes previas.

### Estado anterior detectado

Hoy las deudas se calculan desde operaciones reales:

- deuda de cliente: ventas con medio `Cuenta Corriente`, menos cobros aplicados,
- deuda de proveedor: pagos/proveedores registrados con medio `Cuenta Corriente`, menos cancelaciones aplicadas.

Los modelos base `Cliente` y `Proveedor` no tienen un saldo inicial propio. Ademas, los pagos/cobros actuales aplican contra objetos concretos:

- `CobroDeudaDetalle` aplica contra una `Venta`,
- `CancelacionDeudaProveedorDetalle` aplica contra un `PagoProveedor`.

Por eso no alcanza con agregar un campo decimal simple: tambien hay que permitir que ese saldo inicial se cobre/cancele como una deuda seleccionable.

### Implementacion aplicada

Crear saldos iniciales como documentos de deuda separados, no como una suma suelta.

Para clientes:

- nuevo modelo `SaldoInicialCliente`, ligado a `Cliente`, con monto, fecha, descripcion y usuario opcional,
- nuevo detalle de cobro para aplicar cobros contra ese saldo inicial,
- la API `api_cliente_deudas` debe devolver deudas de ventas y tambien saldos iniciales pendientes,
- la API `api_cobro_deuda` debe aceptar ambos tipos de deuda.

Para proveedores:

- nuevo modelo `SaldoInicialProveedor`, ligado a `Proveedor`, con monto, fecha, descripcion y usuario opcional,
- nuevo detalle de cancelacion para aplicar pagos contra ese saldo inicial,
- la API `api_proveedor_deudas` debe devolver deudas de pagos proveedor y tambien saldos iniciales pendientes,
- la API `api_cancelacion_deuda_proveedor` debe aceptar ambos tipos de deuda.

### Alternativa mas simple, pero menos completa

Agregar solo `saldo_inicial` a `Cliente` y `Proveedor`. No la recomiendo como solucion final porque despues no queda claro contra que se aplica un cobro parcial, y se fuerza logica especial en todos los reportes.

### Archivos a modificar

- `ventas/models.py`
- `compras/models.py`
- `ventas/admin.py`
- `compras/admin.py`
- `pos/views.py`
- `pos/templates/pos/terminal.html`
- nuevas migraciones en `ventas/migrations/` y `compras/migrations/`
- tests en `ventas/tests.py`, `compras/tests.py` o tests especificos de POS si se agregan.

### Reglas funcionales

- El saldo inicial debe poder cargarse desde administracion.
- Debe aparecer en el POS al buscar deudas del cliente/proveedor.
- Debe soportar pago/cobro parcial o total segun la logica actual de seleccion.
- No debe necesitar abrir un turno historico falso.
- No debe contaminar ventas reales ni tickets de venta.

---

## 3. Ocultar completamente las cards de saldos cuando estan bloqueadas

### Pedido

En la vista POS, cuando las cards de saldos estan bloqueadas/ocultas desde configuracion, no mostrarlas directamente para aprovechar espacio.

### Estado anterior detectado

El POS ya tenia una opcion local llamada `Ocultar saldos de las cards`. Antes esa opcion colapsaba cada card y mostraba un boton de desbloqueo por clave, pero la zona de cards seguia ocupando espacio.

### Implementacion aplicada

Cambiar el comportamiento de privacidad:

- si `Ocultar saldos de las cards` esta activo, ocultar todo el contenedor `#saldos-cards`,
- no renderizar cards colapsadas,
- mantener la opcion en configuracion para volver a mostrarlas,
- cuando se desactive la opcion, renderizar nuevamente las cards normales.

Esto deja mas espacio vertical para las operaciones del turno, que es lo que necesita el cajero.

### Archivos a modificar

- `pos/templates/pos/terminal.html`
- posiblemente `README_AJUSTES_POS.md` si se quiere actualizar el comportamiento documentado.

### Validaciones

- Activar ocultar saldos y confirmar que desaparece toda la seccion de cards.
- Desactivar ocultar saldos y confirmar que vuelven a aparecer.
- Confirmar que la lista de operaciones sube y aprovecha el espacio.

---

## 4. Limpiar, ocultar y mostrar movimientos del cajero en POS

### Pedido

Agregar comandos arriba de la tabla/lista de movimientos:

- `Limpiar`, para que el cajero deje la terminal visualmente limpia,
- `Ocultar`, para esconder la lista,
- `Mostrar`, para traer movimientos anteriores si necesita buscar una venta o movimiento.

Los registros deben quedar guardados.

### Implementacion aplicada

Resolverlo como estado visual en el frontend, no como borrado de base de datos.

Comportamiento sugerido:

- `Limpiar`: guarda una marca de tiempo local del turno actual y oculta los movimientos ya vistos. Los movimientos nuevos vuelven a aparecer.
- `Ocultar`: colapsa la lista completa de operaciones.
- `Mostrar`: muestra nuevamente todos los movimientos del turno activo, ignorando la marca de limpieza.

Para que no afecte a otro cajero ni a otro turno, la clave local debe incluir el id del turno:

- ejemplo conceptual: `sfi_pos_ops_clean_after_turno_<turno_id>`.

### Archivos a modificar

- `pos/templates/pos/terminal.html`
- opcionalmente `pos/views.py` si se decide enviar `turno_id` de forma mas explicita en la respuesta de operaciones.

### Validaciones

- Registrar varias operaciones.
- Presionar `Limpiar` y confirmar que la lista queda vacia visualmente.
- Registrar una operacion nueva y confirmar que aparece.
- Presionar `Mostrar` y confirmar que vuelve todo el historial del turno.
- Presionar `Ocultar` y confirmar que la lista se colapsa sin perder datos.
- Recargar navegador y confirmar que el comportamiento se mantiene por turno.

---

## 5. Botonera dinamica de filtros por tipo de movimiento

### Pedido

En la tabla/lista de movimientos del cajero, agregar una botonera que se vaya completando segun los movimientos existentes: pagos, ventas, gastos, retiros, cobros, etc. Debe servir como filtro rapido para segmentar los movimientos del dia.

### Implementacion aplicada

La API `api_ultimas_operaciones` ya devuelve cada operacion con `tipo`, `clase`, descripcion, fecha e importe. Se puede construir la botonera en el frontend a partir de las operaciones recibidas.

Filtros sugeridos:

- `Todos`
- `Ventas`
- `Cobros`
- `Gastos`
- `Proveedor`
- `Deuda proveedor`
- `Pago cuenta`
- `Retiros`

La botonera debe mostrarse solo con tipos presentes en el turno actual. Cada boton puede incluir contador, por ejemplo `Ventas 8`.

### Archivos a modificar

- `pos/templates/pos/terminal.html`
- opcionalmente `pos/views.py` si se prefiere que el backend devuelva labels normalizados y contadores.

### Validaciones

- Con turno sin movimientos: no mostrar filtros o mostrar solo `Todos` deshabilitado.
- Con ventas y gastos: mostrar solo esos filtros.
- Al elegir un filtro: la lista debe cambiar sin pedir datos nuevos al servidor.
- El filtro debe combinar bien con `Limpiar`, `Ocultar` y `Mostrar`.

---

## Orden recomendado de implementacion

Para minimizar riesgo, conviene hacerlo por pasos chicos:

1. QR/red local en version instalada.
2. Ocultar completamente cards cuando la privacidad esta activa.
3. Controles `Limpiar`, `Ocultar`, `Mostrar` de operaciones.
4. Filtros dinamicos de operaciones.
5. Saldos iniciales de clientes/proveedores con migraciones y pruebas.

El punto 5 es el mas delicado porque toca modelo de datos y migraciones. Los puntos 1, 3 y 4 son principalmente runtime/UI. El punto 2 es UI sobre una configuracion que ya existe.

---

## Impacto tecnico por modulo

### `run_server.py`

- Escuchar en `0.0.0.0:8250` en modo instalado.
- Mantener apertura del navegador local en `http://127.0.0.1:8250/pos/`.

### `gestion_de_carnicerias/settings.py`

- Permitir hosts de red local cuando `GESTION_CARNICERIAS_DESKTOP=1`.
- Evitar abrir demasiado el modo desarrollo normal si no corresponde.

### `ventas/models.py`

- Agregar modelo de saldo inicial de cliente.
- Agregar modelo/detalle para aplicar cobros contra ese saldo inicial.

### `compras/models.py`

- Agregar modelo de saldo inicial de proveedor.
- Agregar modelo/detalle para aplicar cancelaciones contra ese saldo inicial.

### `pos/views.py`

- Incluir saldos iniciales en las APIs de deudas.
- Aceptar IDs tipados o payload mixto para cobrar/cancelar deudas de ventas/pagos y saldos iniciales.
- Mantener compatibilidad con el formato actual mientras sea posible.

### `pos/templates/pos/terminal.html`

- Ocultar seccion de cards completa si esta activa la privacidad.
- Agregar toolbar de operaciones: `Limpiar`, `Ocultar`, `Mostrar`.
- Agregar filtros dinamicos por tipo de operacion.
- Ajustar CSS para que el panel use mejor el alto disponible.

### Admin y reportes

- Registrar modelos nuevos de saldos iniciales en admin.
- Verificar que reportes de deuda contemplen los saldos iniciales.
- Si los reportes actuales solo miran ventas/pagos proveedor, extenderlos donde corresponda.

---

## Migraciones previstas

Esta tanda probablemente requiere migraciones solo para el punto de saldos iniciales:

- `ventas/migrations/0007_saldoinicialcliente_cobrodeudasaldoinicialdetalle.py`,
- `compras/migrations/0007_saldoinicialproveedor_and_more.py`.

Los cambios de QR, cards, limpiar/mostrar y filtros no deberian requerir migraciones.

---

## Pruebas recomendadas antes del release

### Backend

- `python manage.py check`
- tests de `ventas`, `compras`, `tesoreria` y `pos` si existen o se agregan.
- prueba manual de migraciones sobre copia de base existente.

### POS manual

- abrir caja,
- registrar venta,
- registrar venta en cuenta corriente,
- cobrar deuda de cliente creada por venta,
- cobrar deuda de cliente creada por saldo inicial,
- registrar deuda proveedor,
- cancelar deuda proveedor creada por operacion,
- cancelar deuda proveedor creada por saldo inicial,
- probar cards ocultas,
- probar limpiar/ocultar/mostrar movimientos,
- probar filtros por tipo,
- probar QR desde celular.

### Build/release Windows

- subir version en `version.py` usando el flujo del proyecto,
- correr migraciones en modo instalado,
- generar instalador con `build_release.bat`,
- verificar hash del instalador,
- instalar sobre una base existente y validar que no se pierden datos.

---

## Riesgos y cuidados

- El acceso por QR depende tambien de la red local y del firewall de Windows.
- `ALLOWED_HOSTS='*'` solo deberia usarse en modo desktop/local, no como regla general para despliegues web.
- Los saldos iniciales deben ser auditables; no conviene que sean solo campos editables sin historial de aplicacion.
- `Limpiar` nunca debe borrar registros ni llamar a deletes en backend.
- Los filtros deben trabajar sobre los movimientos cargados del turno activo del cajero, no sobre datos globales.

---

## Resultado esperado al cerrar la tanda

Al subir esta release, el cajero deberia poder:

- abrir el POS desde celular/tablet escaneando el QR de la app instalada,
- cargar cuentas iniciales de clientes y proveedores,
- trabajar con mas espacio si decide ocultar saldos,
- limpiar visualmente su terminal sin perder historial,
- volver a mostrar operaciones anteriores cuando necesite buscar algo,
- filtrar rapido movimientos del turno por ventas, gastos, pagos, cobros y retiros.
