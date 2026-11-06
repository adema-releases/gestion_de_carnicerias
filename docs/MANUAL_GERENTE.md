# Manual del gerente de sucursal

El gerente puede hacer todo lo de los demás puestos: [mostrador](MANUAL_MOSTRADOR.md), [caja](MANUAL_CAJA_CARNICERIA.md), [recepción y cámara](MANUAL_RECEPCION_Y_CAMARA.md) y [conteo y liquidación](MANUAL_CONTEO_Y_LIQUIDACION.md). Además configura la sucursal desde el **admin** de la PC de la sucursal (`http://<PC>:8250/admin/`).

## Roles

| Rol | Puede | No puede |
| --- | --- | --- |
| Carnicero ayudante | Armar y anular sus comandas, recibir, ver stock, contar | Cobrar, despostar, cerrar conteos |
| Carnicero oficial | Lo del ayudante, más despostar, anular comandas de otros, cerrar conteos y liquidaciones | Cobrar |
| Cajera | Abrir y cerrar caja, cobrar, gastos, retiros, cobros de deuda | Recepción, stock, conteos |
| Gerente | Todo | — |

## Dar de alta a una persona

1. Admin → **Usuarios** → **Agregar**. Poné usuario y clave.
2. En **Perfil, rol y puestos**:
   - Completá el nombre.
   - Elegí el **Rol**. Al guardar se cargan los permisos de ese rol.
   - Elegí los **Puestos habilitados**. Si no elegís ninguno, puede operar en todos.
3. Si hace falta, ajustá permisos sueltos en **Permisos de cajero** (por ejemplo, un ayudante que también puede despostar). Si después le cambiás el rol, los permisos vuelven a ser los del rol nuevo.
4. Si es cajera, asignale los medios de pago en Admin → Tesorería → **Asignaciones de medios de pago a cajeros**: Efectivo, Mercado Pago y Fiado. Sin asignaciones ve todas las cuentas, incluidas las internas.

Para dar de baja a alguien, destildá **Activo** en su usuario. No lo borres: sus ventas y comandas quedan a su nombre.

## Puestos y dispositivos

- Admin → Core → **Puestos**: cada dispositivo es un puesto con nombre y tipo (**Caja**, **Mostrador** o **Recepción**). El tipo decide qué pantalla abre.
- Las tablets y celulares se conectan al wifi de la sucursal y abren la dirección de la PC, por ejemplo `http://192.168.1.20:8250/pos/`. La dirección exacta queda anotada en el registro de la app cuando arranca.
- Cada dispositivo recuerda su puesto. Para cambiarlo, se toca **Puesto** en la pantalla.

## Cámaras

Admin → Recepción → **Cámaras**: nombre, tipo (cámara frigorífica, exhibidora o freezer) y orden. La primera cámara activa de tipo cámara es la que se ofrece al recibir las medias reses. Una cámara que ya no se usa se desactiva; no se borra.

## Día de liquidación

Admin → Core → **Configuración** → **Día de liquidación**. Por defecto es martes; ese día la pestaña Conteo muestra el aviso.

## Sincronización con el frigorífico

- La PC sube lo que pasa en la sucursal y baja catálogo, precios, fotos y despachos, sola, cada minuto.
- Sin internet, la sucursal sigue vendiendo y sube todo cuando vuelve la conexión.
- En **Configuración** están la **última sincronización** y el **último error**. Si el error se repite, avisá al frigorífico.
- Precios, productos y plantillas los cambia el frigorífico. Si se tocan acá, el cambio no sube a la central y se pierde la próxima vez que el frigorífico modifique ese producto.

## Controles de cada semana

1. **Liquidación**: revisá la merma total y los faltantes más caros. Si la merma pasa del 6%, buscá la causa: carne vieja, despostes sin cargar o kilos mal tipeados en las comandas.
2. **Diferencias de caja**: los faltantes y sobrantes de cada cierre, con su motivo. Se regularizan con un **Ajuste de cuenta** ([Manual de turno de caja](CAJA_MANUAL.md)).
3. **Comandas anuladas**: Admin → Ventas → **Comandas**, filtrando por estado. Cada una muestra quién la anuló y el motivo.
