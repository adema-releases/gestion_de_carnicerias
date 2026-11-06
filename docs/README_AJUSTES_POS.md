# Ajustes POS - Guia completa de cambios

## 1. Objetivo general

Durante esta jornada se ajusto el POS para resolver cuatro problemas de fondo:

- simplificar la operatoria del cajero,
- hacer que las cards reflejen realmente el turno activo,
- mejorar la privacidad visual en pantalla,
- hacer que la hora mostrada coincida con la PC instalada.

La idea fue mantener el modelo de datos existente y la separacion contable de cada operacion, pero mejorando la forma en la que el POS presenta y concilia la informacion.

---

## 2. Resumen funcional de lo que cambio

### 2.1. Venta y cobro de deuda

Antes existian botones separados para:

- `Venta`
- `Cobro Deuda`

Ahora el tablero principal conserva un solo ingreso principal para ventas.

Dentro del modal de `Venta` se agrego el acceso:

- `Buscar deudas y cobrarlas`

Eso significa que:

- el cajero entra por `Venta`,
- si esta haciendo una venta comun, la registra normalmente,
- si en realidad necesita cobrar fiado, lo deriva desde el mismo contexto.

### 2.2. Proveedor y pago de cuenta proveedor

Antes existian dos entradas separadas:

- `Proveedor`
- `Pagar Cuenta Prov.`

Ahora el tablero principal deja un solo acceso principal para proveedores.

Dentro del modal de `Proveedor` se agrego el acceso:

- `Buscar cuentas y pagarlas`

Con esto el flujo queda mas parecido al de ventas: una sola puerta de entrada y una derivacion interna para cuenta corriente.

---

## 3. Regla de cuenta corriente

La cuenta corriente ya no depende solo de lo que muestra el HTML, sino tambien de una validacion real en backend.

### 3.1. Cuando la cuenta corriente esta habilitada

Se considera habilitada cuando el usuario tiene al menos un medio de pago asignado cuya categoria sea:

- `Cuenta Corriente`

### 3.2. Cuando la cuenta corriente NO esta habilitada

Si el usuario no tiene ese medio asignado:

- no aparecen accesos de cobro de deudas de clientes,
- no aparecen accesos de pago de cuenta de proveedores,
- las consultas de deudas devuelven vacio,
- las APIs de cancelacion o cobro rechazan la operacion.

Esto evita inconsistencias entre lo que el POS deja ver y lo que realmente puede operar ese cajero.

---

## 4. Conciliacion real de las cards

Este fue uno de los cambios mas importantes.

### 4.1. Problema original

Las cards de medios de pago estaban leyendo informacion desde una logica que servia para flujo de caja, pero no representaba bien todo lo emitido en el turno. Eso producia problemas como:

- mezclar turnos que no correspondian,
- no reflejar correctamente ventas fiadas,
- mostrar saldos que no arrancaban correctamente al abrir un turno nuevo.

### 4.2. Criterio nuevo

Las cards ahora se reconstruyen directamente desde las operaciones reales del turno activo del cajero.

Eso incluye:

- ventas simples,
- ventas multipago,
- ventas en cuenta corriente,
- cobros de deuda,
- gastos,
- pagos a proveedor,
- cancelaciones de deuda proveedor,
- retiros,
- saldo inicial declarado al abrir caja.

### 4.3. Regla por medio de pago

Cada card se calcula sobre el turno activo del cajero.

Regla general:

- todos los medios arrancan en `0`,
- solo `Efectivo` arranca con el `saldo_inicial` declarado,
- luego se suman ingresos y se restan egresos del turno activo.

Formula conceptual:

- `saldo = base + ingresos - egresos`

Donde:

- para `Efectivo`, `base = saldo_inicial del turno`,
- para los demas medios, `base = 0`.

### 4.4. Como se interpreta Cuenta Corriente

La categoria `Cuenta Corriente` no representa caja fisica, pero en el POS se la usa como card de conciliacion comercial del turno.

Por eso ahora:

- si emitis una venta fiada, la card de `Cuenta Corriente` refleja ese importe,
- si luego cobras esa deuda con otro medio, la card del medio real usado para cobrar recibe el ingreso,
- la cuenta corriente del turno muestra lo efectivamente emitido en ese medio durante ese turno.

### 4.5. Turno nuevo

Cuando se abre un turno nuevo:

- la conciliacion de cards usa solo ese turno activo,
- no arrastra ventas ni movimientos de turnos cerrados anteriores,
- `Efectivo` parte del valor declarado en apertura,
- los otros medios arrancan en cero.

Esto corrige el problema de "arranca con cualquier saldo" al abrir una caja nueva el mismo dia.

---

## 5. Alcance exacto del turno mostrado en POS

El POS ahora refleja exclusivamente el turno activo del usuario logueado.

Eso significa que:

- no mezcla turnos de otros cajeros,
- no mezcla turnos cerrados del mismo usuario,
- incluso si el usuario es superadmin, las cards y operaciones del POS representan su caja activa, no un consolidado global del dia.

Este punto era clave para que el titulo `OPERACIONES DEL TURNO` y las cards dijeran exactamente lo mismo que la caja abierta de ese usuario.

---

## 6. Privacidad visual y seguridad

Tambien se trabajo sobre la exposicion de saldos en pantalla.

### 6.1. Opcion de configuracion

Se agrego una opcion en la configuracion del POS para ocultar los saldos de las cards.

La preferencia se guarda en el navegador del equipo actual, para que funcione como modo privacidad local.

### 6.2. Comportamiento en modo privacidad

Cuando esta activo el modo privacidad:

- se oculta toda la seccion de cards,
- no se ve el nombre del medio,
- no se ve la categoria,
- no se ve el saldo ni el detalle de ingresos/egresos,
- el panel de operaciones gana espacio vertical.

### 6.3. Reaparicion de cards

Para volver a ver las cards:

1. abrir configuracion del POS,
2. desactivar `Ocultar saldos de las cards`,
3. guardar.

La seccion vuelve a renderizarse con los saldos actualizados del turno.

---

## 7. Hora local de la PC

Otro problema detectado fue la diferencia entre:

- la hora que mostraba el POS,
- la hora real de la PC donde estaba instalado.

### 7.1. Causa

La UI estaba dependiendo de datos del servidor para mostrar hora y timestamps visibles.

### 7.2. Solucion aplicada

Ahora el POS usa la hora local del navegador/equipo para mostrar:

- reloj del header,
- hora de cada movimiento en la lista,
- fecha y hora de los detalles,
- fecha y hora de impresion en ticket/detalle del POS.

Esto hace que el usuario vea la hora de su maquina instalada, no una hora desplazada por timezone del servidor.

---

## 8. Criterio tecnico aplicado

### 8.1. Lo que NO se cambio

- no se modificaron modelos de negocio para ventas, cobros, pagos o cancelaciones,
- no se cambiaron migraciones para resolver estos ajustes,
- no se unifico todo en una sola tabla nueva,
- no se rompio la separacion entre venta, cobro de deuda, pago proveedor y cancelacion proveedor.

### 8.2. Lo que SI se cambio

- se simplifico la entrada UX del POS,
- se reforzaron reglas de cuenta corriente en backend,
- se rehizo la logica de cards por turno activo,
- se agrego privacidad con validacion de clave,
- se paso a hora local de la PC para lo visible en la UI.

### 8.3. Motivo de esta estrategia

Se eligio corregir comportamiento en la capa POS y en la conciliacion del turno, en vez de rehacer el dominio, porque:

- el modelo actual ya separa correctamente cada operacion,
- el problema estaba mas en representacion y conciliacion que en persistencia,
- el cambio podia resolverse con menor riesgo y sin migraciones adicionales.

---

## 9. Tutorial rapido de uso

### 9.1. Registrar una venta comun

1. Entrar en `Venta`.
2. Cargar importe.
3. Elegir cliente si corresponde.
4. Agregar uno o varios medios de pago.
5. Emitir ticket.

### 9.2. Cobrar una deuda de cliente

1. Entrar en `Venta`.
2. Usar `Buscar deudas y cobrarlas`.
3. Seleccionar cliente.
4. Cargar deudas.
5. Elegir medio real con el que paga.
6. Registrar cobro.

### 9.3. Registrar un pago a proveedor

1. Entrar en `Proveedor`.
2. Elegir proveedor.
3. Cargar importe.
4. Elegir medio.
5. Registrar.

### 9.4. Pagar deuda de proveedor

1. Entrar en `Proveedor`.
2. Usar `Buscar cuentas y pagarlas`.
3. Seleccionar proveedor.
4. Cargar deudas.
5. Elegir medio real de cancelacion.
6. Registrar pago.

### 9.5. Activar modo privacidad en cards

1. Abrir configuracion del POS.
2. Activar `Ocultar saldos de las cards`.
3. Guardar.

### 9.6. Volver a mostrar cards protegidas

1. Abrir configuracion del POS.
2. Desactivar `Ocultar saldos de las cards`.
3. Guardar.

---

## 10. Archivos principales tocados

- `pos/views.py`
- `pos/templates/pos/terminal.html`
- `pos/urls.py`
- `tesoreria/tests.py`
- `README_AJUSTES_POS.md`

Tambien se apoyan en la logica ya existente de:

- `tesoreria/signals.py`
- `tesoreria/models.py`

---

## 11. Validaciones realizadas

Durante estos cambios se validaron estos puntos:

- chequeo general de Django con `manage.py check`,
- tests de tesoreria con `manage.py test tesoreria.tests`,
- prueba de conciliacion por turno activo,
- prueba de cuenta corriente reflejada en cards,
- prueba de reseteo correcto de cards al abrir nuevo turno,
- prueba de ocultado completo y reaparicion de la seccion de cards.

---

## 12. Resultado esperado final

Al terminar todos estos ajustes, el comportamiento correcto del POS es este:

- el tablero tiene menos botones y una entrada mas simple,
- las deudas de clientes y proveedores se operan desde venta/proveedor,
- la cuenta corriente solo aparece cuando el usuario realmente puede usarla,
- las cards reflejan el turno activo del cajero,
- el efectivo arranca del saldo declarado y el resto en cero,
- cuenta corriente refleja lo emitido en ese medio durante el turno,
- la hora visible coincide con la PC instalada,
- los saldos pueden ocultarse quitando toda la seccion de cards del POS.