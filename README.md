# Gestion de Carnicerias

Gestion de Carnicerias es un sistema Django para un frigorifico que distribuye carne a sus propias carnicerias. Cada sucursal corre la app en su PC y vende sin internet: mostrador que arma comandas, caja que las cobra, recepcion de medias reses, desposte, stock por corte, camaras y liquidacion semanal. Una instancia central en la nube recibe lo de todas las sucursales, les manda catalogo, precios y despachos, y lleva la cuenta corriente de cada una.

La base es una app de caja con tesoreria, cuentas corrientes de clientes y proveedores, reportes PDF/Excel, Django Admin con Jazzmin e internacionalizacion; esas partes siguen vigentes y se describen mas abajo.

## Manuales por puesto

Para usar el sistema en una carnicería (mostrador, caja, recepción, conteo y liquidación, gerente y central del frigorífico), ver [docs/MANUALES.md](docs/MANUALES.md).

**Documentación completa con capturas, en español y en chino:** [documentacion/](documentacion/README.md) — 27 tutoriales paso a paso por puesto, la idea del negocio, conceptos, referencia y preguntas frecuentes. Las capturas se regeneran con scripts sobre una base de demo (ver [documentacion/_herramientas/](documentacion/_herramientas/README.md)).

## Despliegue de la central (Docker / Coolify)

La central corre en Docker: `Dockerfile` + `docker-compose.yml` (central + PostgreSQL). Las sucursales siguen con la app de escritorio de Windows. Paso a paso, variables y backups en [docs/DESPLIEGUE_COOLIFY.md](docs/DESPLIEGUE_COOLIFY.md).

## Objetivo funcional

En cada sucursal:

- Armar comandas por peso en el mostrador y cobrarlas en caja.
- Recibir despachos y remitos, pesar cada media res con foto del visor y despostarla con plantillas.
- Llevar stock por corte, medias reses por camara, conteos y la liquidacion semanal con balance de kilos.
- Sincronizar con la central cada minuto, sin depender de internet para vender.

En la central:

- Despachar a cada sucursal y llevar su cuenta corriente (despachos, remesas, ajustes).
- Mantener catalogo, precios, fotos y plantillas de despiece para todas las sucursales.
- Ver el panel con ventas, kilos, mermas, liquidaciones y saldo de cada sucursal.

Heredado de la app de caja:

- Abrir y cerrar turnos de caja.
- Registrar ventas con uno o varios medios de pago.
- Registrar gastos, retiros de efectivo y pagos a proveedores.
- Gestionar clientes y proveedores activos.
- Manejar cuentas corrientes de clientes y proveedores.
- Consultar resumenes, conciliacion por medios de pago y reportes de cierre.
- Administrar catalogos desde Django Admin.

## Stack tecnico

```text
Python 3.13
Django 5.2
PostgreSQL (psycopg2), en la sucursal y en la central
requests (agente de sincronizacion)
Pillow (fotos)
django-jazzmin
django-import-export
django-solo
python-dotenv
ReportLab
openpyxl
```

## Estructura del proyecto

```text
gestion_de_carnicerias/ Configuracion global, URLs, WSGI/ASGI y dashboard admin.
core/            Configuracion, sucursales, puestos, roles y permisos POS, identidad global y sincronizacion.
tesoreria/       Medios de pago, asignaciones por cajero y libro de movimientos de cuentas.
inventario/      Categorias, productos (precio, unidad, foto) y movimientos de stock.
ventas/          Turnos de caja, ventas con lineas por producto, comandas, clientes, cobros y retiros.
compras/         Proveedores, pagos a proveedores y cancelaciones de deuda.
gastos/          Categorias de gasto y egresos operativos.
recepcion/       Plantillas de despiece, remitos, medias reses, desposte, camaras, conteos y liquidacion.
central/         Despachos, cuenta corriente de sucursales, panel central y API de sincronizacion.
pos/             Pantallas de mostrador, caja, recepcion y puesto, con sus endpoints JSON.
dashboard/       Tablero de metricas (/dash/).
agente/          Asistente con IA integrado (/agente/).
templates/       Overrides de admin, login y vistas HTML.
static/          CSS y JavaScript de la interfaz.
locale/          Catalogos gettext: espanol y chino simplificado (ingles y portugues no se ofrecen).
media/           Fotos de productos, remitos y visores de balanza.
docs/            Manuales por puesto (docs/MANUALES.md) y notas tecnicas.
```

## Arquitectura general

La arquitectura se organiza alrededor de cinco capas:

1. Configuracion global: `gestion_de_carnicerias/settings.py` define apps, middleware, static/media, Jazzmin, autenticacion e idiomas.
2. Dominio: cada app declara sus entidades en `models.py`, con relaciones Django ORM y metadata traducible.
3. Administracion: cada app registra sus modelos en `admin.py` para operar catalogos, busquedas, filtros e import/export.
4. Operacion POS: `pos/` expone las pantallas de cada puesto y APIs JSON protegidas por login y permisos de cajero.
5. Reportes: `gestion_de_carnicerias/admin_override.py` y helpers del POS generan dashboard, Excel y PDF.

### Sucursal y central

La misma app corre en dos modos, segun `SYNC_MODO`:

- `sucursal`: la PC de cada carniceria. Vende sin internet y guarda cada cambio en una cola (`core.CambioSync`).
- `central`: el servidor del frigorifico. Recibe lo de todas las sucursales y publica catalogo, precios, plantillas y despachos.

Reglas de la sincronizacion (`core/sincronizacion.py`, `core/agente_sync.py`, `central/api.py`):

- Cada registro tiene un `uuid` global; los de sucursal llevan ademas su `sucursal` (`core.sync.DeSucursalMixin`). La clave primaria local sigue siendo entera.
- Cada dato tiene un solo dueno. La sucursal escribe sus operaciones (ventas, comandas, turnos, recepciones, despostes, stock, camaras, conteos). La central escribe catalogo, precios, fotos, plantillas, despachos y cuenta corriente.
- La sucursal se identifica con `Authorization: Bearer <token_sync>`. La central fuerza la sucursal del token en todo lo que recibe y rechaza cambios sobre registros de otra.
- Las referencias viajan por `uuid`, `username` o `app.modelo`. Un lote se aplica en varias vueltas hasta resolverlas; durante la aplicacion se pausan las senales (`core.sync_estado.aplicando_sync`).
- Endpoints: `GET /sync/estado/`, `POST /sync/subir/`, `GET /sync/bajar/?desde=<cursor>`.
- `run_server.py` lanza el agente cada 60 segundos si `SYNC_URL` y `SYNC_TOKEN` estan configurados. A mano: `python manage.py sincronizar` (`--inicial` para una sucursal que ya tenia datos, `--catalogo` para subir el catalogo local a una central vacia, `--loop N` para repetir).

## Mejora POS: cajon monedero por venta en efectivo

Se agrego la apertura automatica del cajon monedero (RJ11/RJ12 conectado a la impresora) cuando una venta incluye efectivo.

### Que se hizo

- Se agrego el comando ESC/POS de pulso a cajon (`ESC p`) y un helper dedicado en [pos/printing.py](pos/printing.py).
- Se reutilizo el canal RAW de Windows (pywin32) para enviar el pulso sin afectar la impresion.
- Se invoca la apertura desde la API de venta cuando el pago incluye efectivo, tanto en pago unico como multi-medio, en [pos/views.py](pos/views.py).

### Detalle tecnico

- Comando usado: `ESC p m t1 t2` con valores `1B 70 00 19 FA` (pulso estandar para cajon en la mayoria de impresoras ESC/POS).
- Se envia como trabajo RAW independiente (no mezclado con el ticket) para evitar que el corte o el buffer del ticket afecten el pulso.
- La funcion no bloquea la venta: si no hay impresora configurada o no esta `pywin32`, se registra warning y la venta continua.

### Configuracion requerida

1. Cargar el nombre exacto de la impresora en `Configuracion.nombre_impresora` (UI del POS o Admin).
2. Asegurar que la impresora este instalada en Windows y que el cajon este conectado al puerto RJ11/RJ12.
3. Tener `pywin32` instalado en el entorno (requerido para imprimir y abrir el cajon).

### Cuando se dispara

- Venta con pago unico en `Efectivo`.
- Venta con pagos multiples donde al menos uno es `Efectivo` y el importe es mayor a 0.

### Pruebas rapidas

1. Registrar una venta con medio `Efectivo` y confirmar que el cajon abre.
2. Registrar una venta solo con tarjeta/transferencia y confirmar que el cajon no abre.
3. Desconfigurar impresora y verificar que la venta no falla (solo queda warning en logs).

## Novedades release 0.6.0: adelantos de clientes

Se agregaron mejoras para auditoria, impresion y anulacion segura de adelantos de clientes.

### Ticket de adelantos en POS

- El modal de cuenta corriente de clientes ahora incluye el boton `Ticket Adelantos`.
- Se agrego el endpoint `POST /pos/api/clientes/<id>/adelantos/ticket/` para imprimir el ticket.
- El ticket lista adelantos del cliente, en que operaciones se compensaron y totales (`recibido`, `aplicado`, `disponible`).
- Los totales operativos del ticket se calculan solo sobre adelantos activos.
- Si existe un adelanto anulado, se imprime su estado y la trazabilidad de anulacion (usuario, fecha, motivo, monto revertido y destinos).

### Anulacion segura desde Django Admin

- En `AdelantoCliente` se agrego la accion de admin `Revertir y anular adelantos`.
- La accion des-aplica cobros relacionados y marca el adelanto como `anulado` con `anulado_en`, `anulado_por` y `motivo_anulacion`.
- Se registra un evento por anulacion en `AdelantoClienteAnulacionEvento`, incluyendo detalle tecnico para auditoria.
- Guardrails de seguridad:
   - Bloquea anulaciones cuando el cobro tuvo dinero real (`monto_recibido > 0`).
   - Bloquea anulaciones cuando un cobro usa adelantos fuera del set seleccionado.

### Consistencia de saldos y ledger

- `saldo_disponible` de adelantos anulados pasa a 0.
- Los saldos de cuenta corriente, cierres y reportes operativos excluyen adelantos anulados.
- Las senales de tesoreria limpian y no regeneran `MovimientoCuenta` para adelantos anulados.
- El estado de cuenta PDF marca `ANULADO` y muestra trazabilidad de eventos cuando corresponde.

## Internacionalizacion

El sistema se ve en **espanol** (por defecto) o en **chino simplificado** (中文):

```python
LANGUAGE_CODE = 'es'
LANGUAGES = [
    ('es', _('Spanish')),
    ('zh-hans', _('Chinese')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
```

Los catalogos de ingles y portugues siguen en `locale/` pero no se ofrecen.

### Como se elige el idioma

- Cada usuario tiene su idioma en `UserProfile.idioma`. Lo cambia con el selector **ES / 中文** (en mostrador, caja, recepcion, elegir puesto, login, dashboard, panel central y la barra del admin) o lo fija el gerente al crear el usuario en el admin.
- `core.middleware.UserLanguageMiddleware` (despues de `AuthenticationMiddleware`) activa el idioma del perfil en cada pedido, incluidas las APIs: los mensajes de error tambien salen traducidos. Asi la misma PC muestra el idioma de quien inicio sesion.
- Sin sesion (login) se usa la cookie del ultimo idioma elegido en esa PC y, si no hay, espanol. El idioma del navegador no se tiene en cuenta.
- `core.views.cambiar_idioma` reemplaza a `set_language` de Django (misma URL `i18n/setlang/` y parametro `language`) para guardar en el perfil ademas de la cookie.
- El asistente IA contesta en el idioma del usuario.

**Siempre en espanol:** tickets impresos, PDF y Excel (`pos.views._en_espanol`). El ticket lo recibe el cliente, las termicas ESC/POS no suelen tener fuente china y los PDF usan Helvetica. Tambien quedan como se cargaron los datos (nombres de productos, categorias, medios de pago, clientes).

### Donde estan los textos

- Python: `gettext()` / `gettext_lazy()` (los `msgid` de modelos estan en ingles o espanol; los de las vistas, en espanol).
- Templates: `{% trans %}` / `{% blocktrans %}`, tambien dentro del JS inline. Los `<script>` con traducciones van envueltos en `{% autoescape off %}` para que el texto no salga escapado como HTML; en JS los valores variables quedan dentro del msgid como `${variable}` y el traductor los mueve de lugar.
- JS estatico (`static/js/*.js`): `gettext()` del catalogo de Django (`/jsi18n/`, dominio `djangojs`).
- En el JS de la caja, el bloque del ticket impreso esta entre `/* i18n-off */` y `/* i18n-on */`.

**Regla para las traducciones al chino:** no usar comillas ASCII (`'` `"` `` ` ``) ni `\` — van dentro de literales JS y los romperian. Usar “” o 「」. Mantener igual los placeholders (`%(nombre)s`, `%s`, `%%`, `${...}`) y las etiquetas HTML. `core/test_idioma.py` lo verifica sobre el `.mo` compilado.

### Actualizar traducciones

1. Envolver los textos nuevos (`gettext('...')` en Python, `{% trans "..." %}` en templates).
2. Extraer (con el venv activo; requiere GNU gettext en el PATH):

   ```powershell
   $ig = '--ignore=venv/*','--ignore=staticfiles/*','--ignore=static/admin/*','--ignore=static/jazzmin/*','--ignore=static/import_export/*','--ignore=media/*'
   python manage.py makemessages -l zh_Hans -l es @ig
   python manage.py makemessages -d djangojs -l zh_Hans -l es @ig
   ```

3. Completar en `locale/zh_Hans/LC_MESSAGES/django.po` (y `djangojs.po`) las entradas con `msgstr ""` o marcadas `#, fuzzy` (revisarlas y borrar la marca). En `es` no hace falta traducir los `msgid` que ya estan en espanol.
4. Compilar y probar:

   ```powershell
   python manage.py compilemessages -l es -l zh_Hans --ignore=venv
   python manage.py test core.test_idioma
   ```

5. Reiniciar el servidor. `build_release.bat` compila las traducciones antes de empaquetar.

### Bootstrap del sistema (datos iniciales)

Para dejar el sistema listo despues de clonar el repo o resetear la base:

```powershell
# con la base PostgreSQL creada y vacia (ver "Base de datos y migraciones")
python manage.py init_system
python manage.py seed_carniceria   # opcional: datos de ejemplo
```

`seed_carniceria` carga una carniceria de ejemplo: catalogo con precio por kilo, plantillas de despiece, camaras, puestos, una persona por rol (`gerente1`, `cajera1`, `oficial1`, `ayudante1`, clave `Carne1234`), 14 dias de ventas con comandas, remitos y despostes, y una liquidacion cerrada el dia de liquidacion anterior. La de hoy queda sin hacer, para probarla. Se niega a correr si ya hay ventas, salvo con `--force`.

El comando `init_system` corre las migraciones y crea: 3 medios de pago
(Efectivo, Mercado Pago, Fiado), categorias de gasto basicas (Luz,
Alquiler, Sueldos, Gastos Generales), un superadmin
(`ADEMASISTEMAS` / `Adema123`) y dos cajeros (`cajero1` / `cajero2`,
clave `Cajero1234`) sin permiso para crear o editar
clientes/proveedores/categorias.

Flags utiles:

- `--reset` borra y recrea los usuarios y medios definidos por el script.
- `--skip-migrate` omite `migrate` cuando la base ya esta migrada.

## Modelo de dominio

### Core

`core` contiene objetos transversales del sistema:

- `Configuracion`: datos generales del negocio, sucursal de esta instalacion, dia de liquidacion y estado de la sincronizacion (cursor, ultima, ultimo error).
- `Sucursal`: codigo, nombre, supermercado y `token_sync` (se genera solo). Vive en la central; la sucursal local adopta su identidad al sincronizar.
- `Puesto`: dispositivo con nombre y tipo (caja, mostrador, recepcion). Una cookie recuerda el puesto de cada navegador y decide que pantalla abre `/pos/`.
- `UserProfile`: datos extendidos del usuario, `rol` (ayudante, oficial, cajera, gerente) y puestos habilitados. Elegir o cambiar el rol carga los permisos de `core/roles.py`.
- `PermisosCajero`: permisos granulares para habilitar o bloquear acciones del POS.
- `CambioSync`: cola de cambios por sincronizar (modelo, uuid, operacion).

> Nota: el catalogo `MedioDePago` se movio de `core` a la nueva app `tesoreria` (ver seccion *Tesoreria*). La tabla fisica sigue siendo `core_mediodepago`, por lo que no hace falta migrar datos existentes.

### Tesoreria

`tesoreria` centraliza el dinero. Tiene tres responsabilidades:

- **`MedioDePago`** (movido desde `core`): catalogo de medios con `categoria` funcional (Efectivo, Cuenta Corriente, Tarjeta de Credito/Debito, Transferencia Bancaria, Otro). Para preservar los datos existentes mantiene `db_table = 'core_mediodepago'`.
- **`AsignacionMedioPagoCajero`**: relacion `User` ↔ `MedioDePago` con bandera `activo`. Determina que medios puede usar cada cajero en el POS.
- **`MovimientoCuenta`**: libro de movimientos. Cada venta, gasto, pago a proveedor, cobro de deuda, cancelacion, retiro o apertura de turno genera filas aqui.

#### Asignaciones por cajero

- Si el cajero **no tiene** ninguna asignacion, ve **todos** los medios (compatibilidad hacia atras).
- Si tiene asignaciones, solo puede operar sobre los `activo=True`.
- Los superusuarios siempre ven el catalogo completo.
- Las APIs del POS validan el medio en cada operacion y devuelven `403` si no esta permitido.

La funcion `tesoreria.models.medios_permitidos_para(user)` encapsula la regla y se usa tanto en la vista del terminal como en cada endpoint JSON.

#### Libro `MovimientoCuenta`

Cada movimiento guarda:

- `fecha`, `tipo` (`venta`, `venta_pago`, `gasto`, `pago_proveedor`, `cobro_deuda`, `cancelacion_proveedor`, `retiro`, `apertura_caja`, `ajuste`).
- `signo` (`ingreso` o `egreso`) y `monto` (siempre positivo).
- `medio_de_pago` (PROTECT), `usuario`, `turno` (FK a `ventas.TurnoCaja`).
- Origen tipado mediante `GenericForeignKey` (`content_type` + `object_id`) que apunta al objeto fuente (Venta, Gasto, etc).

Las senales de `tesoreria.signals` regeneran de forma **idempotente** los movimientos asociados a cada objeto fuente: ante un `post_save` borran los movimientos previos del objeto y los recrean a partir del estado actual. Esto asegura que editar o eliminar una venta deja el ledger consistente sin duplicados.

Reglas clave:

- Una venta con un solo medio genera un movimiento `tipo=venta`.
- Una venta con `VentaPago` (multipago) genera un movimiento `tipo=venta_pago` por cada linea.
- Las operaciones contra **Cuenta Corriente** *no* generan movimientos (representan deuda, no movimiento de dinero):
  - Venta a CC.
  - Linea de multipago en CC.
  - Pago a proveedor en CC (es una deuda emitida).
- La cancelacion de deuda de proveedor y el cobro de deuda de cliente sí generan movimiento (con el medio efectivamente usado).
- El retiro de efectivo siempre se imputa a Efectivo.
- La apertura de turno con `saldo_inicial > 0` crea un ingreso `tipo=apertura_caja` sobre Efectivo.

#### Tarjetas de saldo en el POS

La terminal muestra una grilla de tarjetas, una por cada medio asignado al cajero, con:

- Saldo del dia (suma de ingresos − egresos sobre los turnos del dia del cajero).
- Detalle de ingresos y egresos.
- Color por categoria (Efectivo verde, Tarjeta azul, Transferencia violeta, etc.).

Comportamiento del saldo inicial:

- **Efectivo**: arranca con el `saldo_inicial` del turno (apertura genera el primer movimiento).
- **Tarjeta / Mercado Pago / otros**: arrancan en `$0` y suman segun se registren ventas.

El backend lo calcula en `pos.views._saldos_medios_dia` y lo expone dentro de `api_ultimas_operaciones` bajo la clave `saldos_medios`. El frontend lo renderiza en `renderSaldosMedios` cada vez que se refrescan las operaciones.

Las categorias funcionales se mantienen como claves historicas en la base de datos para no romper datos existentes. La etiqueta visible se traduce con gettext.

### Inventario

`inventario` contiene el catalogo y el stock:

- `Categoria`: rubros (Vacuno, Cerdo, Pollo, Achuras, Embutidos, Elaborados, Almacen…).
- `Producto`: nombre, rubro, unidad (kg o unidad), precio, activo y foto para el boton del mostrador.
- `MovimientoStock`: entrada o salida con signo (recepcion, desposte, venta, ajuste, merma), apuntando por referencia generica a la operacion que la genero. El stock de un producto es la suma de sus movimientos (`inventario/stock.py`). Cada `VentaItem` regenera su movimiento al guardarse o borrarse (`inventario/signals.py`).

### Recepcion

`recepcion` cubre todo lo que entra a la sucursal y su control:

- `PlantillaDespiece` / `PlantillaLinea`: porcentaje de cada corte, grasa, hueso y recorte por tipo de media res, y la merma no vendible.
- `Remito`, `MediaRes`, `RemitoItem`: lo recibido. Cada media res guarda peso del remito, peso al colgarla, foto del visor, camara y estado. Un remito puede venir de un `central.Despacho`.
- `Desposte` / `DesposteLinea`: kilos teoricos por plantilla (peso x (1 - merma%) x porcentaje) y, si se pesaron, los reales; la diferencia con el peso de entrada es la merma de desposte.
- `Camara`: camara frigorifica, exhibidora o freezer, con orden.
- `Conteo` / `ConteoLinea`: conteo fisico por camara (lo que queda y lo que se tira, con motivo). Puede ser de control o liquidacion semanal. Al cerrarlo, el stock queda igual a lo contado; la liquidacion ademas guarda el balance de kilos del periodo (`recepcion/liquidacion.py`):

```text
stock inicial + recibido - vendido - merma de desposte - descarte + diferencia de conteo = stock final
```

### Central

`central` vive en la instancia central:

- `Despacho`, `DespachoMedia`, `DespachoItem`: lo que sale del frigorifico hacia cada sucursal, con peso de salida y precio de transferencia. Pasa a `recibido` cuando la sucursal sube el remito que lo recibe.
- `MovimientoCuentaSucursal`: cuenta corriente de cada sucursal. Despacho suma deuda; remesa la baja (se carga en positivo y se guarda negativa); ajuste corrige.
- Panel `/central/` (staff): ultima sync, ventas, kilos, diferencia contra remito, merma de desposte, medias en camara, ultima liquidacion y merma de la semana, comandas abiertas, despachos sin recibir y saldo, por sucursal.

### Ventas

`ventas` concentra el flujo de ingresos:

- `TurnoCaja`: representa una jornada o sesion de caja abierta por un usuario.
- `Cliente`: cliente activo con telefono y notas.
- `Venta`: operacion de venta con ticket secuencial por turno.
- `VentaItem`: linea por producto (cantidad, precio unitario, subtotal); es la que baja stock.
- `VentaPago`: linea de pago para soportar multiples medios en una misma venta.
- `Comanda` / `ComandaItem`: lo que arma el mostrador. Numero diario por sucursal; estado abierta, cobrada o anulada. Se cobra una sola vez: si dos cajas la toman a la vez, la segunda recibe `409`.
- `RetiroEfectivo`: salida de efectivo desde caja.
- `CobroDeuda`: cabecera de cobro de deuda de cliente.
- `CobroDeudaDetalle`: aplicacion de un cobro sobre ventas en cuenta corriente.

La propiedad `saldo_pendiente` de `Venta` calcula deuda restante comparando importe de venta contra detalles de cobro.

### Compras

`compras` gestiona proveedores y deudas:

- `Proveedor`: proveedor activo con telefono y notas.
- `PagoProveedor`: pago o deuda emitida a proveedor.
- `CancelacionDeudaProveedor`: cabecera de cancelacion de deuda a proveedor.
- `CancelacionDeudaProveedorDetalle`: aplicacion de una cancelacion sobre deudas previas.

La propiedad `saldo_pendiente` de `PagoProveedor` calcula deuda restante contra cancelaciones aplicadas.

### Gastos

`gastos` contiene egresos operativos:

- `CategoriaGasto`: catalogo de clasificacion de gastos.
- `Gasto`: gasto asociado a turno, categoria opcional, importe y medio de pago.

## Flujo POS

`/pos/` abre la pantalla del puesto del dispositivo (`pos/puestos.py`); sin puesto elegido, `/pos/puesto/` lo pide:

| Puesto | Pantalla | Que hace |
| --- | --- | --- |
| Mostrador | `pos/templates/pos/mostrador.html` (`pos/comandas.py`) | Botones de producto con foto, pesaje, envio de la comanda a caja, mis comandas del dia |
| Caja | `pos/templates/pos/terminal.html` (`pos/views.py`) | Turno de caja; la venta trae comandas en espera y suma productos por unidad |
| Recepcion | `pos/templates/pos/recepcion.html` (`pos/recepcion_views.py`, `pos/conteo_views.py`) | Recibir, camara y desposte, stock, conteo y liquidacion |

Endpoints nuevos para la carniceria:

- Comandas: `api/comandas/` (crear), `api/comandas/pendientes/`, `api/comandas/mias/`, `api/comandas/<id>/anular/`.
- Recepcion: `api/recepcion/datos/`, `api/remitos/` (multipart con fotos), `api/camara/`, `api/camara/<id>/despostar/`, `api/camara/<id>/mover/`, `api/stock/`.
- Conteo: `api/conteo/`, `api/conteo/iniciar/`, `api/conteo/<id>/linea/`, `api/conteo/<id>/resumen/`, `api/conteo/<id>/cerrar/`, `api/conteo/<id>/anular/`.

La terminal de caja vive en `pos/templates/pos/terminal.html` y se sirve desde `pos.views.terminal`. La vista carga datos iniciales como categorias, medios, clientes, proveedores, turno activo, permisos y configuracion del negocio.

El modal de venta carga las categorias con un pad de ritmo rapido (`pos/templates/pos/_venta_categorias.html`): categoria, importe, otra categoria, importe, hasta cerrar la venta. El total sale de la suma del desglose. Si el negocio no tiene categorias cargadas, el pad no se muestra. Ver `docs/README_MODAL_VENTA_RAPIDA.md`.

Las operaciones se exponen por endpoints JSON:

- `api_turno_estado`: consulta turno abierto.
- `api_abrir_turno`: abre caja con saldo inicial.
- `api_cerrar_turno`: cierra caja y devuelve URL de PDF.
- `api_venta`: registra ventas simples, multipago o con desglose por varias categorias.
- `api_gasto`: registra gastos.
- `api_pago_proveedor`: registra pago o deuda a proveedor.
- `api_cobro_deuda`: cancela deuda de cliente.
- `api_cancelacion_deuda_proveedor`: cancela deuda de proveedor.
- `api_retiro`: registra retiro de efectivo.
- `api_ultimas_operaciones`: devuelve actividad y totales del dia.
- `api_detalle_operacion`: devuelve detalle imprimible o consultable.
- `api_cliente_adelantos_imprimir_ticket`: imprime ticket de adelantos de cliente con trazabilidad.

Los decoradores internos `_require_permiso` y `_require_turno_ok` centralizan las validaciones antes de modificar datos. Adicionalmente `_check_medio` valida que el medio de pago utilizado en la operacion este permitido para el cajero (ver *Tesoreria*).

`api_ultimas_operaciones` devuelve, ademas de los listados, la clave `saldos_medios` con una tarjeta por medio asignado al cajero (saldo del dia, ingresos y egresos). La terminal usa estos datos para pintar las tarjetas en la parte superior del panel de operaciones.

## Permisos

Los permisos de caja viven en `PermisosCajero` y son evaluados desde el POS. Los superusuarios tienen todos los permisos activos. Si un usuario no tiene registro de permisos, el sistema permite operar por defecto para conservar compatibilidad.

Permisos disponibles:

- Registrar ventas.
- Registrar gastos.
- Pagar proveedores o cancelar cuentas.
- Registrar retiros de efectivo.
- Cobrar deuda de cliente.
- Crear o editar clientes.
- Crear o editar proveedores.
- Crear categorias de venta.
- Abrir o cerrar caja.
- Armar comandas y anular comandas de otros.
- Recibir mercaderia, despostar y ver stock.
- Contar stock (sin ver el esperado) y cerrar conteos y liquidaciones.

Cada rol de `core/roles.py` trae su combinacion; el detalle por rol esta en [docs/MANUAL_GERENTE.md](docs/MANUAL_GERENTE.md).

## Dashboard y reportes

`gestion_de_carnicerias/admin_override.py` reemplaza el index de Django Admin con un dashboard propio. Calcula metricas por rango de fechas y cajero:

- Ventas.
- Gastos.
- Cobros.
- Pagos a proveedores.
- Deuda emitida de clientes y proveedores.
- Balance general.
- Series diarias para graficos.
- Distribucion por cajero, medio de pago y categoria.

Tambien expone exportaciones:

- Excel con hojas de resumen, ventas, gastos, medios de pago y cajeros.
- PDF de dashboard.
- PDF de estado de cuenta para clientes y proveedores.
- PDF de cierre de turno desde POS.

## Admin

Jazzmin personaliza el Admin y agrupa las apps principales. `gestion_de_carnicerias/settings.py` define titulos, logos, iconos, orden del menu y modelos ocultos. `django-import-export` esta habilitado en catalogos y movimientos donde conviene importar o exportar datos.

Convenciones actuales:

- Los modelos exponen `verbose_name`, `verbose_name_plural` y `help_text` traducibles.
- Los listados usan `list_display`, `list_filter`, `search_fields` y `date_hierarchy` cuando aplica.
- Las columnas calculadas usan `@admin.display`.
- Los inlines de cobros y cancelaciones son de solo lectura para proteger el historial aplicado.

## Base de datos y migraciones

El proyecto usa PostgreSQL, tanto en la sucursal como en la central. La conexion se arma con las variables `DB_*` del `.env`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'gestion_de_carnicerias'),
        'USER': os.environ.get('DB_USER', 'kevin'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}
```

Crear la base (una por instalacion; para probar sucursal y central en la misma PC, dos bases):

```powershell
psql -U postgres -h localhost -c "CREATE DATABASE gestion_de_carnicerias OWNER kevin ENCODING 'UTF8'"
```

### App de escritorio (PC de la sucursal)

El instalador de Windows trae su propio PostgreSQL: no hace falta instalarlo aparte.

- `build_release.bat` copia `bin`, `lib` y `share` de un PostgreSQL 18 (de `PGSQL_HOME` o de `C:\Program Files\PostgreSQL\18`) a `vendor\pgsql`, y `installer.nsi` los instala en `<instalacion>\pgsql`.
- Al arrancar, `run_server.py` (con `postgres_local.py`) crea la primera vez un cluster en `C:\GestionDeCarnicerias\pgdata`. Escucha solo en `127.0.0.1:5433`, con usuario `carnicerias` y una clave generada que queda en `db\clave_postgres.txt`. Despues crea la base y corre `init_system`; en las siguientes, `migrate`.
- La app arranca PostgreSQL al abrir y lo apaga al salir desde la bandeja. Si se corta de golpe, la proxima vez lo encuentra corriendo y lo reusa.
- La configuracion de cada PC esta en `C:\GestionDeCarnicerias\config.env`, que se crea la primera vez con `SYNC_MODO`, `SYNC_URL` y `SYNC_TOKEN`. Si ahi se define `DB_HOST`, la app usa ese servidor en lugar del propio.
- `run_server.py --servidor` corre sin bandeja ni navegador, en primer plano. `--migrate-only` deja la base lista y sale; lo usa el instalador.
- Para probar el runtime sin tocar `C:\`: `GDC_DATA_ROOT` (carpeta de datos), `GDC_PGSQL_DIR` (binarios) y `GDC_PORT` (puerto de la app).
- Si una version futura trae otra version mayor de PostgreSQL, la app se niega a arrancar con los datos viejos: antes hay que correr `pg_upgrade`.

Despues de cambios en modelos:

```bash
python manage.py makemigrations
python manage.py migrate
```

Las migraciones recientes normalizan metadata de modelos para internacionalizacion y agregan `help_text` sin cambiar el significado de los datos existentes.

### Movimiento de `MedioDePago` a `tesoreria`

La reubicacion del modelo se hace mediante `migrations.SeparateDatabaseAndState` para no tocar la tabla fisica:

- `tesoreria/0001_initial`: declara `MedioDePago` en el estado de Django con `db_table='core_mediodepago'` (state-only).
- `compras/0005_retarget_mediodepago`, `ventas/0005_retarget_mediodepago`, `gastos/0003_retarget_mediodepago`: alteran *solo* el estado de las FKs para apuntar a `tesoreria.mediodepago`.
- `core/0004_remove_mediodepago`: borra `MedioDePago` del estado de `core` (state-only).

Resultado: en bases existentes basta con `python manage.py migrate`; no hay `ALTER TABLE`, no se pierden datos y todas las FKs siguen apuntando a la misma tabla.

## Tests

La suite completa corre con:

```bash
python manage.py test
```

Son unos 305 tests, unos 7 minutos. Hoy falla uno que ya fallaba antes de las fases de carniceria: `pos.tests.TraduccionesSaldosInicialesTests.test_nombres_de_saldos_iniciales_estan_en_espanol`.

Los de la carniceria:

- `pos/test_comandas.py`: comandas, cobro unico, anulacion, puestos.
- `recepcion/tests.py`: despiece, remitos, desposte y stock.
- `recepcion/test_liquidacion.py`: camaras, conteo ciego, liquidacion y balance de kilos, API de conteo.
- `central/tests.py`: cola de cambios, lotes en otra base, API central (token, sucursal forzada, catalogo, despachos por sucursal).

La suite de tesoreria (`python manage.py test tesoreria`) cubre asignaciones por cajero, ventas simples y multipago, exclusion de Cuenta Corriente, gastos, retiros, apertura de turno, cobros y cancelaciones, idempotencia de la regeneracion y el endpoint `saldos_medios` del POS.

Tambien se agrego cobertura para:

- Reversion y anulacion de adelantos de cliente con guardrails de integridad.
- Impresion del ticket de adelantos de cliente con trazabilidad de anulacion.

## Variables de entorno

El archivo `.env` se carga con `python-dotenv`.

Tiene que estar en UTF-8: `Add-Content` de PowerShell lo guarda en otra codificacion y `python-dotenv` falla al leerlo.

```env
SECRET_KEY=tu-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8250

# Base de datos
DB_NAME=gestion_de_carnicerias
DB_USER=kevin
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432

# Sincronizacion
SYNC_MODO=sucursal              # o central
SYNC_URL=https://<central>      # solo en la sucursal
SYNC_TOKEN=<token de la sucursal, del admin de la central>

# Puerto de runserver (por defecto 8250)
RUNSERVER_PORT=8250
```

Solo en el servidor (las fija el `Dockerfile`; ver [docs/DESPLIEGUE_COOLIFY.md](docs/DESPLIEGUE_COOLIFY.md)):

| Variable | Efecto |
| --- | --- |
| `DATABASE_URL` | `postgres://usuario:clave@host:5432/base`; si está, reemplaza a las `DB_*`. |
| `BEHIND_HTTPS_PROXY=1` | Confía en `X-Forwarded-Proto` del proxy y marca las cookies como seguras. |
| `SERVIR_MEDIA=1` | Sirve `/media/` sin `DEBUG`. |
| `DATA_UPLOAD_MAX_MEMORY_SIZE_MB` | Tamaño máximo de un pedido (por defecto 2,5; la central usa 100 por los lotes con fotos). |
| `DB_CONN_MAX_AGE` | Segundos que se reusa la conexión a la base (por defecto 0). |

Con `SYNC_MODO=central` y `DEBUG` apagado, la app no arranca si `SECRET_KEY` es la de desarrollo. Con `whitenoise` instalado (solo en `requirements.txt`, no en el build de Windows) Django sirve los estáticos.

## Comandos utiles

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py runserver            # escucha en 0.0.0.0:8250 (o RUNSERVER_PORT)
python manage.py seed_carniceria      # datos de ejemplo
python manage.py sincronizar          # una sincronizacion con la central
python manage.py sincronizar --loop 60
python manage.py makemessages -l es -l pt -l zh_Hans --ignore=venv/* --ignore=.venv/* --ignore=staticfiles/*
python manage.py compilemessages --ignore=venv/* --ignore=.venv/*
```

## Convenciones de mantenimiento

- Nuevos textos visibles deben envolver etiquetas con `_()` desde `django.utils.translation`.
- Nuevos campos de modelos deben declarar `verbose_name` y `help_text`.
- Las claves historicas almacenadas en base de datos no deben traducirse directamente; se traducen sus etiquetas visibles.
- Las APIs del POS deben devolver JSON estable para no romper el JavaScript existente.
- Los cambios de estructura deben ir acompanados por migraciones.
- La documentacion debe reflejar el sistema real antes que patrones genericos.
