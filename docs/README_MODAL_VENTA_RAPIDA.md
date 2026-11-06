# Modal de venta rapida guiada

Este documento describe el nuevo modal opcional de `Nueva Venta`, pensado para registrar ventas desde el POS con menos distraccion y mejor uso en celular.

El flujo clasico sigue existiendo y queda activo por defecto. El modal rapido solo aparece cuando se habilita el permiso correspondiente para el usuario.

## Objetivo

Simplificar el registro de ventas comunes sin romper el flujo actual de quienes ya usan el sistema.

La idea principal es convertir la venta en un flujo guiado de tres pasos:

1. Importe.
2. Cliente.
3. Pago.

Las acciones secundarias, como cobrar deudas o registrar adelantos, quedan disponibles pero fuera del camino principal para no distraer al cajero durante una venta simple.

## Activacion por permiso

El flujo rapido se controla desde el modelo `PermisosCajero` con el campo:

```text
usar_flujo_venta_guiado
```

Regla importante:

- por defecto es `False`;
- el flujo clasico se mantiene si no se activa;
- tambien queda apagado por defecto para superusuarios, para evitar cambios inesperados;
- se puede activar desde el admin de permisos del cajero.

Archivos principales:

- `core/models.py`: agrega el permiso `usar_flujo_venta_guiado`.
- `core/admin.py`: permite verlo y editarlo desde el admin.
- `core/migrations/0008_permisoscajero_usar_flujo_venta_guiado.py`: migracion del nuevo permiso.
- `pos/views.py`: expone el permiso al template del POS.
- `pos/templates/pos/terminal.html`: decide si renderiza el modal clasico o el guiado.

## Flujo del modal rapido

### 1. Paso Importe

El cajero ingresa el importe total de la venta.

Tambien tiene accesos rapidos para montos frecuentes:

- `$500`
- `$1.000`
- `$2.000`
- `$5.000`
- `Otro`

Si no existen categorias de venta, este paso se mantiene como un campo simple: el pad de
categorias no se renderiza.

Si existen categorias, debajo del importe aparece el pad de carga rapida por categorias
(ver `Pad de categorias`). El importe total pasa a ser el acumulado de las lineas cargadas.

### 2. Paso Cliente

Por defecto la venta queda como:

```text
Consumidor final
```

Si se elige un cliente, el POS habilita tambien medios como `Cuenta Corriente` cuando correspondan.

En este paso quedan las acciones secundarias relacionadas con cuenta corriente:

- `Buscar deudas`
- `Registrar adelanto`

Estas acciones no estan en el primer paso porque no forman parte de una venta comun. Se mantienen accesibles, pero fuera del flujo principal.

### 3. Paso Pago

El cajero elige el medio de pago.

Para una venta simple, tocar un medio cubre automaticamente el total de la venta con ese medio.

Ejemplo:

```text
Importe: $1.500
Medio: Efectivo
Resultado: Efectivo $1.500
```

## Pago mixto

El paso de pago tambien permite cargar mas de un medio.

Para usarlo:

1. Tocar `Pago mixto`.
2. Elegir un medio.
3. Ingresar el importe de ese medio.
4. Tocar `Agregar`.
5. Elegir otro medio.
6. Ingresar el saldo restante, o un importe mayor si corresponde vuelto.
7. Registrar la venta.

Ejemplo sin vuelto:

```text
Total venta: $1.500
Efectivo: $1.000
Mercado Pago: $500
Resultado: venta registrada con 2 medios de pago
```

Ejemplo con vuelto:

```text
Total venta: $1.500
Mercado Pago: $500
Efectivo: $1.200
Total pagado: $1.700
Vuelto: $200
```

Reglas del pago mixto:

- el total pagado debe cubrir el importe de la venta;
- si el total pagado supera la venta y hay efectivo, el POS muestra `Vuelto`;
- si el total pagado supera la venta sin efectivo, el POS muestra `Excedente`;
- cada medio se guarda como una fila independiente en `VentaPago`;
- el medio principal de la venta queda como el medio de mayor importe, por compatibilidad con reportes existentes.

## Pad de categorias

Los dos modales (clasico y guiado) comparten el mismo componente:

```text
pos/templates/pos/_venta_categorias.html
```

Si no hay categorias cargadas, el include no renderiza nada y la pantalla queda simple.

El ritmo de carga es: categoria -> importe -> otra categoria -> importe, hasta terminar.

1. Tocar una categoria (o buscarla por nombre y confirmar con Enter).
2. Escribir el importe en la fila que aparece.
3. Enter (o `Agregar`) confirma la linea y deja el pad listo para la siguiente categoria.
4. Repetir por cada categoria de la venta.

Detalles de la interaccion:

- cada boton de categoria muestra el importe acumulado que ya tiene asignado;
- tocar dos veces la misma categoria suma sobre la linea existente, no la duplica;
- el buscador aparece recien cuando hay mas de 6 categorias, y con el foco inicial puesto
  ahi en el flujo clasico la venta se carga entera con teclado;
- si el cajero primero escribe el importe total, el pad sugiere el importe restante en cada
  categoria y avisa `Falta asignar $X de $Y`;
- el campo `Importe Total` queda de solo lectura mientras haya lineas cargadas: el total es
  la suma del desglose;
- si quedo una categoria elegida con importe escrito pero sin confirmar, se toma igual al
  registrar la venta.

Ejemplo:

```text
Almacen: $1.200
Limpieza: $200
Total venta: $1.400
```

Para que esto sea reportable, no se guarda como texto en la descripcion. Se agrego el modelo:

```text
VentaCategoriaDetalle
```

Cada fila guarda:

- venta;
- categoria;
- importe asignado a esa categoria.

Archivos principales:

- `pos/templates/pos/_venta_categorias.html`: pad de carga rapida, compartido por los dos modales.
- `ventas/models.py`: modelo `VentaCategoriaDetalle`.
- `ventas/migrations/0012_ventacategoriadetalle.py`: migracion de la tabla.
- `ventas/admin.py`: muestra el desglose como inline dentro de la venta.
- `pos/views.py`: valida y guarda el desglose recibido desde el POS.
- `gestion_de_carnicerias/admin_override.py`: suma ventas por categorias usando el desglose nuevo y conserva compatibilidad con ventas antiguas.

Reglas de validacion:

- cada linea debe tener categoria e importe mayor a cero;
- la suma de las categorias debe coincidir con el total de la venta;
- si hay una sola categoria, tambien se mantiene `Venta.categoria` como categoria principal;
- si hay mas de una categoria, `Venta.categoria` queda vacia y el detalle queda en `VentaCategoriaDetalle`.

## Compatibilidad con el flujo clasico

El modal clasico no se elimina.

Si `usar_flujo_venta_guiado` esta apagado:

- se muestra el modal anterior, con el pad de categorias en la columna izquierda;
- sigue exigiendo categoria cuando existen categorias: hay que asignar el importe a por lo
  menos una;
- sigue usando el mismo endpoint `/pos/api/venta/`;
- las ventas historicas siguen funcionando con `Venta.categoria`.

Si `usar_flujo_venta_guiado` esta encendido:

- se muestra el modal rapido, con el pad de categorias debajo del importe en el paso 1;
- la categoria sigue siendo opcional en el flujo principal;
- el cobro de deudas y adelantos quedan como acciones secundarias en el paso Cliente.

En los dos casos el POS manda siempre el desglose en `categorias` y ya no usa el campo
`categoria_id` del payload clasico.

## APIs y backend

El endpoint usado sigue siendo:

```text
/pos/api/venta/
```

Payload clasico compatible:

```json
{
  "importe": "1500",
  "categoria_id": 1,
  "cliente_id": null,
  "descripcion": "",
  "pagos": [
    {"medio_id": 1, "importe": 1500}
  ]
}
```

Payload nuevo con categorias multiples:

```json
{
  "importe": "1400",
  "cliente_id": null,
  "descripcion": "",
  "pagos": [
    {"medio_id": 1, "importe": 1000},
    {"medio_id": 2, "importe": 400}
  ],
  "categorias": [
    {"categoria_id": 1, "importe": 1200},
    {"categoria_id": 2, "importe": 200}
  ]
}
```

El backend crea la venta, los pagos y los detalles de categoria dentro de una transaccion atomica.

## Pruebas cubiertas

Se agregaron pruebas en `pos/tests.py` para validar:

- el flujo guiado esta apagado por defecto;
- el modal guiado renderiza cuando se activa el permiso;
- el desglose de categorias se guarda correctamente;
- se rechaza un desglose cuya suma no coincide con el total;
- el pago mixto guarda dos medios en `VentaPago`;
- el detalle de operacion devuelve todos los medios y calcula vuelto cuando hay efectivo.

Comandos usados para validar:

```bash
python manage.py test pos.tests.VentaGuiadaPosTests
python manage.py test pos gestion_de_carnicerias tesoreria
```

## Criterio de uso recomendado

Activar `usar_flujo_venta_guiado` en cajeros o instalaciones donde se priorice:

- velocidad de carga;
- uso en celular;
- ventas simples con pocos datos obligatorios;
- separacion clara entre venta comun y operaciones de cuenta corriente.

Mantener el flujo clasico cuando el negocio ya opera comodo con el modal anterior o necesita ver todos los campos al mismo tiempo.