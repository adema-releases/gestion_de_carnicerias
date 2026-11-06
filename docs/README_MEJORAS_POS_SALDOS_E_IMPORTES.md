# Mejoras POS - cards de saldos e importes escritos

Este documento resume las mejoras implementadas en el POS para controlar mejor la visibilidad de las cards de saldos y evitar cambios accidentales en campos de importe por el scroll del mouse.

## 1. Objetivo

Se ajustaron dos puntos de uso diario del POS:

- permitir ahorrar espacio mostrando u ocultando las cards de saldos del turno;
- proteger la privacidad de los importes de esas cards mostrando puntos despues de unos segundos;
- quitar los controles de subir/bajar de algunos campos de importe para evitar que el scroll modifique valores sin querer.
- permitir configurar los importes favoritos del modal de venta rapida.

La idea general es que el cajero tenga una pantalla mas limpia y que los importes sensibles no queden visibles permanentemente si no hace falta.

---

## 2. Configuracion de cards de saldos

Se actualizo el modal `Configuracion POS`.

Ahora incluye la opcion:

- `Mostrar cards de saldos`

Este check controla la fila completa de cards de saldos.

Cuando esta activado:

- las cards aparecen debajo de los botones principales del POS;
- se habilita una segunda configuracion para privacidad de valores.

Cuando esta desactivado:

- se oculta toda la fila de cards;
- el POS gana espacio vertical para operaciones y acciones principales.

---

## 3. Auto-ocultado del valor de las cards

Si `Mostrar cards de saldos` esta activo, el modal muestra una segunda opcion:

- `Ocultar el valor del card de saldo luego de X segundos`

Debajo se muestra el campo:

- `Segundos visibles`

El valor por defecto es `3` segundos.

Funcionamiento:

1. Las cards se muestran normalmente con los importes reales.
2. Si el auto-ocultado esta activo, despues de los segundos configurados los importes pasan a verse como puntos.
3. Las cards siguen visibles, pero el valor queda protegido visualmente.

Ejemplo visual:

```text
$7.500  ->  $....
```

---

## 4. Toggle rapido del header

Tambien se ajusto el boton rapido del header, el que combina el icono de ojo y billetera.

El comportamiento ahora depende del estado actual:

- si las cards estan ocultas, el boton las muestra completas;
- si las cards estan visibles pero los importes estan en puntos, el boton muestra los saldos reales;
- si las cards estan visibles y los importes estan visibles, el boton oculta toda la fila de cards.

Esto permite usar un solo control rapido para las dos necesidades:

- recuperar espacio en pantalla;
- ver momentaneamente los saldos cuando estan protegidos.

---

## 5. Importes favoritos del modal de venta rapida

Se agrego una configuracion editable para los botones rapidos del modal de venta guiada.

En `Configuracion` ahora existe el campo:

- `Importes rapidos de venta`

El cliente puede indicar los valores separados por coma, por ejemplo:

```text
500,1000,2000,5000,10000
```

Tambien acepta puntos de miles en importes enteros:

```text
1.000,2.000,5.000
```

Si el campo queda vacio, el POS usa los importes por defecto:

```text
500,1000,2000,5000
```

Los botones del modal se generan automaticamente con esos valores y mantienen el boton `Otro` para escribir un importe manual.

---

## 6. Campos de importe sin spinner

Se quitaron los widgets nativos de subir/bajar en campos de importe donde el scroll podia modificar el numero accidentalmente.

Los campos cambiados dejaron de usar `type="number"` y pasaron a usar:

```html
type="text" inputmode="decimal"
```

Esto mantiene el teclado numerico/decimal en dispositivos compatibles, pero evita las flechas del navegador y evita cambios por rueda del mouse.

## 7. Modales alcanzados

Se aplico en:

- `Cobro de Deudas`: campo `Importe pagado`.
- `Pago de Cuenta Proveedor`: campo `Importe pagado`.
- `Adelanto de Cliente`: campo `Importe del adelanto`.
- `Adelanto a Proveedor`: campo `Importe del adelanto`.

---

## 8. Lectura de importes escritos

Como los campos pasaron a ser texto, se agrego una lectura controlada del importe desde JavaScript.

El parser acepta formatos comunes:

```text
1500
1500.50
1500,50
1.500,50
1,500.50
```

Luego normaliza el valor antes de calcular resumenes o enviarlo al backend.

Esto se usa para:

- calcular faltantes y vueltos en cobro de deudas;
- calcular faltantes y diferencias en pago de cuenta proveedor;
- validar adelantos de cliente;
- validar adelantos de proveedor.

---

## 9. Archivos principales modificados

Las mejoras quedaron concentradas en:

- `pos/templates/pos/terminal.html`
- `pos/views.py`
- `core/models.py`
- `core/forms.py`
- `core/migrations/0009_configuracion_importes_rapidos_venta.py`

---

## 10. Validacion realizada

Se ejecuto la validacion general de Django:

```powershell
.\venv\Scripts\python.exe .\manage.py check
```

Resultado:

```text
System check identified no issues (0 silenced).
```
