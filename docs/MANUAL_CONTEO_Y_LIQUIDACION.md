# Manual de conteo y liquidación

Para el ayudante, el oficial y el gerente. Se usa en **Recepción → Conteo**.

Hay dos tipos de conteo:

| Tipo | Cuándo | Qué se cuenta | Qué cierra |
| --- | --- | --- | --- |
| **Liquidación semanal** | El día de liquidación (martes, salvo que se cambie en Configuración) | Todo lo que tiene stock y se vende por kilo, en todas las cámaras | El balance de kilos de la semana |
| **Conteo de control** | Cuando haga falta revisar algo | Solo los productos que se quieran revisar | Nada; solo ajusta lo contado |

Solo puede haber un conteo abierto por vez.

## Quién hace qué

- **Contar** (ayudante, oficial, gerente): carga lo que queda y lo que se tira. No ve cuánto debería haber; así el conteo es honesto.
- **Cerrar** (oficial y gerente): ve las diferencias contra lo esperado, el balance de kilos y la plata, y cierra.

## El martes, en orden

1. Antes de abrir, el oficial entra a **Conteo** y toca **Liquidación semanal**. El aviso naranja recuerda que es día de liquidación.
2. Ayudante y oficial cuentan, cámara por cámara (ver abajo). Pueden contar a la vez en dos tablets, cada uno en una cámara.
3. El oficial o el gerente toca **Ver diferencias y cerrar**, revisa y cierra.
4. Recién ahí se recibe la carne fresca, se cuelga y se desposta.
5. Se abre el mostrador.

## Contar

1. Arriba, elegí la cámara que estás contando: **Cámara 1**, **Exhibidora** o **Freezer**.
2. Buscá cada producto que hay en esa cámara y cargá:
   - **Queda**: lo que está bien y sigue a la venta, en kilos o unidades.
   - **Se tira**: lo que se descarta.
   - **Motivo**: obligatorio si se tira algo. Puede ser vencido, olor o color; golpeado o quemado por frío; limpieza o recorte sin venta; decomiso; otro.
3. Cada número se guarda solo al salir del casillero: aparece ✓. Si aparece **!**, falta el motivo o hubo un error; corregilo.
4. Con Enter pasás al casillero siguiente.
5. Cambiá de cámara y repetí. Si un producto está en dos cámaras, se carga en cada una; el total se suma solo.

Los productos marcados **contar** tienen stock y hay que contarlos sí o sí en la liquidación. Si no queda nada de uno, cargá **0**. El tilde **Solo los que faltan contar** deja a la vista nada más que esos.

Para borrar una línea mal cargada, vaciá los dos casilleros.

## Ver diferencias y cerrar (oficial y gerente)

1. Tocá **Ver diferencias y cerrar**.
2. Si falta contar algún producto obligatorio, arriba aparece la lista y no se puede cerrar.
3. En la liquidación aparece el **balance de kilos** desde la liquidación anterior:

   ```
   Había al cierre anterior
   + Recibido (medias y productos)
   − Vendido
   − Merma de desposte
   − Se tiró
   ± Faltante o sobrante de conteo
   = Queda
   ```

   La **merma total** suma la merma de desposte, lo tirado y el faltante. Se muestra en kilos y como porcentaje de lo que hubo en la semana; en rojo si pasa el 6%.
4. La tabla muestra cada producto: esperado, queda, se tira y diferencia, en kilos y en pesos. Arriba quedan los faltantes más caros.
5. Escribí una observación si hace falta y tocá **Cerrar liquidación y ajustar stock**.

Al cerrar, el stock queda igual a lo contado: lo tirado sale como merma y la diferencia como ajuste. No se puede deshacer. El balance sube a la central con la próxima sincronización.

El esperado se calcula en el momento de abrir el resumen. Si se vende algo entre que se contó y que se cierra, la diferencia se mueve: por eso conviene liquidar antes de abrir.

## Anular y consultar

- **Anular** (oficial y gerente) borra un conteo abierto con todo lo cargado; el stock no cambia.
- En **Liquidaciones y conteos anteriores** está el historial con la merma y las diferencias de cada uno. Con **Ver** se abre el detalle completo.
