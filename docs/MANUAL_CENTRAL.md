# Manual de la central (frigorífico)

Para quien despacha y controla las sucursales desde el frigorífico. La central es la misma app instalada en un servidor con `SYNC_MODO=central`. Se usa desde el **admin** (`/admin/`) y el **panel central** (`/central/`), con un usuario de staff.

Para instalarla en un servidor con Docker / Coolify, ver [Despliegue de la central en Coolify](DESPLIEGUE_COOLIFY.md).

## Quién escribe qué

| Lo escribe la central | Lo escribe cada sucursal |
| --- | --- |
| Productos, precios y fotos | Ventas, comandas y turnos de caja |
| Categorías y plantillas de despiece | Recepciones, despostes y stock |
| Despachos | Cámaras, conteos y liquidaciones |
| Cuenta corriente de cada sucursal | Personal y puestos |

Lo de la central baja a las sucursales y lo de cada sucursal sube a la central, cada minuto, cuando hay internet. Cada dato se cambia solo donde se escribe. Si la central toca una venta, el cambio no llega a la sucursal. Si una sucursal toca un precio, el cambio no sube y se pierde la próxima vez que la central modifique ese producto.

## Panel central, cada mañana

`/central/` muestra una fila por sucursal. Se recarga sola cada 2 minutos.

| Columna | Qué mirar |
| --- | --- |
| Última sync | En verde, hace menos de 10 minutos. Naranja, de 10 a 60 minutos. Rojo, más de una hora o nunca: la PC está apagada o sin internet. |
| Ventas hoy / 7 días, kg vendidos | Comparar contra las otras sucursales y contra la semana anterior. |
| Medias en cámara | Cuántas medias quedan colgadas y sus kilos. |
| Kg recibidos y dif. vs remito | Kilos pesados al colgar menos el peso de salida. En rojo si llegó más de 1 kg menos. |
| Merma desposte | En naranja si pasa del 4%. |
| Últ. liquidación | En naranja si pasaron más de 8 días o nunca liquidó. |
| Merma semana | La de la última liquidación: desposte + tirado + faltante. Naranja si pasa del 4%; rojo si pasa del 6%. Abajo, kilos tirados y faltantes. |
| Despachos sin recibir | Despachos que la sucursal todavía no confirmó. |
| Saldo cuenta | Lo que la sucursal le debe al frigorífico. |

## Despachar a una sucursal

1. Admin → Central → **Despachos** → **Agregar**.
2. Elegí la sucursal y poné el número de remito de salida.
3. En **Medias reses despachadas**, una fila por media: tipo (plantilla), garrón, peso de salida y precio por kilo.
4. En **Productos despachados**, lo demás: producto, cantidad y precio unitario.
5. Guardá. El total del despacho entra como deuda en la cuenta de la sucursal; si después corregís el despacho, la deuda se ajusta.

En la próxima sincronización, la sucursal ve el despacho en **Despachos por recibir**. Cuando lo confirma, el despacho pasa a **recibido** y los pesos reales llegan al panel.

## Cuenta corriente

Admin → Central → **Cuenta corriente de sucursales**:

- **Remesa**: lo que la sucursal manda (efectivo, transferencia). Se carga en positivo y el sistema lo resta de la deuda.
- **Ajuste**: correcciones, con descripción. Positivo suma deuda; negativo la baja.
- Los despachos se cargan solos; no hace falta registrarlos acá.

## Catálogo

- Admin → Inventario → **Productos**: nombre, rubro, unidad (kg o unidad), precio, activo y **foto**. La foto conviene apaisada, de unos 600 px. Un producto que no se vende más se desactiva; no se borra.
- Admin → Inventario → **Categorías**: los rubros que se ven en el mostrador.
- Admin → Recepción → **Plantillas de despiece**: los porcentajes de cada corte por tipo de media res, más la merma no vendible. Las líneas tienen que sumar 100%; si no, se marcan con ⚠.

Todo cambio baja a todas las sucursales en la próxima sincronización. Los créditos de las fotos tomadas de Wikimedia están en `media/productos/CREDITOS.md`.

## Abrir una sucursal nueva

1. Admin → Core → **Sucursales** → **Agregar**: código, nombre y supermercado. Al guardar se genera el **token de sincronización**.
2. En la PC de la sucursal, corré el instalador (`GestionDeCarnicerias_Installer_vX.Y.Z.exe`). Trae su propio PostgreSQL, deja la app arrancando sola al iniciar sesión y abre el puerto 8250 en el firewall para las tablets.
3. Editá `C:\GestionDeCarnicerias\config.env` en esa PC:

   ```env
   SYNC_MODO=sucursal
   SYNC_URL=https://<dirección de la central>
   SYNC_TOKEN=<token de la sucursal>
   ```

4. Cerrá la app desde el ícono de la bandeja y abrila de nuevo. En el primer minuto baja todo el catálogo.
5. Cargá el personal y los puestos en esa sucursal ([Manual del gerente](MANUAL_GERENTE.md)).

Si la PC ya tenía datos de antes, sin sincronizar, corré una vez `python manage.py sincronizar --inicial` para subirlos.

## Pasar a la nube una sucursal que ya trabaja sola

Cuando la sucursal arrancó con su propia base (sin central) y después se quiere conectar a una nube que se cargó por separado, **no alcanza con poner el token**: cada base tiene sus propios identificadores (uuid) y la sincronización choca. Se copia la base de la sucursal a la nube, pisando lo que haya, y después se conectan:

1. **Con el local cerrado**, en la PC de la sucursal: menú Inicio → *GestionDeCarnicerias* → **Exportar respaldo**. Deja un `.zip` en `C:\GestionDeCarnicerias\respaldos` y abre esa carpeta. (También: admin → menú del usuario → *Respaldo de la base* → **Descargar respaldo**.)
2. En Coolify, **Redeploy** de la nube, para que tenga la misma versión que la sucursal (o más nueva).
3. En la nube: admin → menú del usuario → **Respaldo de la base** → subí el `.zip`, escribí `BORRAR TODO` y **Restaurar**. Se borra todo lo de la nube (también usuarios y claves) y queda igual a la sucursal, con las fotos.
4. La pantalla muestra, para cada sucursal, las tres líneas para su `config.env` (`SYNC_MODO`, `SYNC_URL`, `SYNC_TOKEN`). Copialas en `C:\GestionDeCarnicerias\config.env` de la PC de la sucursal.
5. Cerrá la app desde el ícono de la bandeja y abrila de nuevo. En un minuto sincroniza; desde ahí suben solas las ventas y cajas.

Desde ese momento los **precios y productos se cambian en la nube** (bajan solos a la sucursal); un precio cambiado en la sucursal no sube.

Lo que hace la restauración: reemplaza todos los datos dentro de una transacción (si algo falla, la base queda como estaba), copia las fotos, vacía la cola de cambios pendientes y pone en cero el cursor de sincronización (lo restaurado es el punto de partida), y en la nube genera el token de cada sucursal que no tenga. Un respaldo de una versión más nueva que la instalación de destino se rechaza sin tocar nada.

Por consola: `python manage.py exportar_base [--salida archivo.zip]` y `python manage.py restaurar_base archivo.zip --borrar-todo`.

## Revisar las liquidaciones

Admin → Recepción → **Conteos y liquidaciones**, filtrando por sucursal. Cada liquidación guarda el balance de kilos, la merma total, el valor de lo tirado y de la diferencia, y el detalle por cámara de lo que se contó y tiró, con su motivo. Es de solo lectura: el cierre se hace en la sucursal.
