# Changelog

## Sin publicar

### Added

- Primer deploy en la nube con datos: `DATOS_INICIALES=frigorifico_uno` + `CLAVE_INICIAL_PERSONAL` hacen que el contenedor, con la base vacía, cargue Frigorífico Uno (`inicializar_nube`: `init_system` + `seed_frigorifico_uno`, fotos en `/data/media`). En los redeploys no toca nada. En la nube no quedan claves conocidas: el personal usa `CLAVE_INICIAL_PERSONAL` y `ADEMASISTEMAS` toma `DJANGO_SUPERUSER_PASSWORD` o queda sin clave. Guía: sección 10 de `docs/DESPLIEGUE_COOLIFY.md`.

## 0.0.8 - 2026-11-04

### Added

- **Cargar datos de Frigorífico Uno desde el admin**, sin consola: el superadmin entra a *Usuario → Cargar datos de Frigorífico Uno* (`/admin/system/frigorifico-uno/`), aprieta el botón y ve en pantalla lo que se cargó (sucursales, medios de pago, puestos, usuarios, catálogo con códigos y fotos). No borra ni pisa nada, se puede repetir.

### Changed

- La seed se llama `seed_frigorifico_uno` (`python manage.py seed_frigorifico_uno`, o `GestionDeCarnicerias.exe --alta-frigorifico-uno`). `seed_catan` y `--alta-catan` siguen funcionando.

## 0.0.7 - 2026-11-04

### Added

- Ticket de cierre de caja por la térmica del POS: al cerrar la caja con la impresión activada (⚙ del POS) sale, además del PDF, un ticket con el arqueo de efectivo (saldo inicial, ingresos, egresos, esperado, contado y diferencia con su motivo), ventas e ingresos, egresos, cada medio de pago con movimientos y el neto del turno, con renglón para la firma. Respeta el ancho del papel (58 u 80 mm). Si la impresora falla, la caja queda cerrada igual y se avisa; el ⚙ tiene **Reimprimir último cierre de caja** (`/pos/api/turno/imprimir-ultimo-cierre/`).

### Changed

- El PDF y el ticket del cierre salen del mismo cálculo (`pos.views._datos_cierre`), así no pueden mostrar números distintos.

## 0.0.5 - 2026-11-04

### Fixed

- En la app instalada, **Imprimir ticket de prueba** fallaba con "No module named 'win32timezone'": pywin32 lo importa recién al leer la cola de la impresora y PyInstaller no lo incluía. Ahora va en el spec.

## 0.0.4 - 2026-11-04

### Added

- El mostrador imprime la comanda al enviarla a caja, para dársela al cliente: número grande, fecha y hora, quién atendió, cada producto con su precio por kilo, TOTAL y un código de barras CODE128 (`CM` + id, ej. `CM000012`) con "Presentar en caja" y "No valido como factura". La cajera escanea ese código (con la venta abierta o cerrada) y la comanda se carga sola. Si la impresora falla, la comanda queda enviada igual y se avisa; en "Mis comandas de hoy" hay un botón para reimprimir (`/pos/api/comandas/<id>/imprimir/`).
- Impresora por puesto (`Puesto.impresora` y `Puesto.ancho_papel`, en Administración → Puestos): cada mostrador o caja imprime en la suya. Sirve también si el mostrador es otra PC o una tablet, siempre que la impresora esté instalada en la PC donde corre el sistema. Vacía = la impresora de la Configuración.

## 0.0.3 - 2026-11-04

### Changed

- El modal de venta de la caja entra entero en la pantalla de la PC (desde 901 px de ancho): sin scroll general, la grilla de productos se estira y scrollea por dentro, la columna de pago se compacta y Cancelar / Registrar venta quedan siempre a la vista. Las líneas cargadas scrollean aparte cuando son muchas.
- Fotos propias para Chorizo parrillero (parrillero fino), Chorizo bombón y Chorizo premium.

### Fixed

- Con el modal a pantalla completa las cards de productos se encimaban y los chips de rubro se cortaban: la grilla aplastaba las filas porque las cards (con `overflow: hidden`) no tenían alto mínimo.

## 0.0.2 - 2026-11-04

### Added

- Botón **Imprimir ticket de prueba** en el ⚙ del POS (`/pos/api/probar-impresora/`): prueba el nombre escrito aunque no esté guardado y explica qué pasó. Antes el POS decía "Impreso correctamente" apenas Windows aceptaba el trabajo, aunque la cola fuera de una impresora desenchufada (el trabajo quedaba esperando) o de OneNote / Imprimir a PDF (se perdía sin error). Ahora avisa si el nombre no existe en la PC, si no es una impresora física (puerto `nul:`, `PORTPROMPT:`, fax), si Windows la tiene sin conexión o si la prueba quedó trabada en la cola; en ese caso la cancela para que no salga horas después.
- Ticket de venta para rollos de 58 mm: el ⚙ del POS tiene **Ancho del papel** (58 u 80 mm, se guarda por PC; 80 mm por defecto, como antes). En 58 mm el ticket usa 32 columnas. Vale también para los tickets de cuenta corriente, de adelantos y de prueba.
- El ticket de venta lista cada producto en dos renglones (nombre y `x 2,500 kg`; abajo el precio por kilo o por unidad, `$ 13.900/kg` o `$ 1.500 c/u`, y el importe a la derecha), el TOTAL con el importe pegado al borde derecho, todo alineado a la izquierda, separadores de borde a borde y los medios de pago con los primeros 14 caracteres y el monto a la derecha. Los importes salen como `$ 16.200`. Si la venta tiene productos ya no repite los rubros ni la descripción armada con ellos; queda lo que escribió el cajero o el número de comanda (`nota_ticket` en el detalle de la operación, que ahora trae `items`).
- Alta real de Frigorífico Uno (`python manage.py seed_catan`, o `GestionDeCarnicerias.exe --alta-catan` con la app cerrada): Depósito Central Catan (tipo depósito) y Diana Catan (sucursal, cliente interno del depósito y sucursal de la instalación), medios de pago con tarjeta de débito, crédito y transferencia, puestos Caja 1 y Mostrador 1, personal por rol (dueno, encargado, cajera1, vendedor1) y el catálogo real de la lista de precios (73 productos; los que no tienen precio quedan inactivos). No carga ventas de ejemplo, no pisa datos existentes y desactiva los cajeros genéricos de `init_system` que nunca abrieron caja.
- `Sucursal.tipo`: depósito central o sucursal (cliente interno). Lo que el depósito entrega a una sucursal es una transferencia, no una venta externa.
- Caja con catálogo como el mostrador: el modal de venta se agranda y muestra los productos en cards con foto, código y precio, con chips por rubro. El cobro por rubro sin elegir producto queda en una sección plegable.
- Escaneo y carga por código en la caja: `Producto.codigo` (código de la lista de precios, ej. 601) y `Producto.codigo_barras` (EAN del envase). Escribir o escanear el código + Enter carga el producto: por unidad suma 1 sin preguntar, por kilo pide el peso. Escanear con la venta cerrada la abre con ese producto. El mostrador también busca por código.
- `seed_catan` carga el código de cada producto y una foto ilustrativa a 46 cortes (`inventario/fotos_catalogo`, viaja en el instalador); no pisa fotos ni códigos ya cargados.
- Despliegue de la central en Docker / Coolify: `Dockerfile` (gunicorn, whitenoise, traducciones compiladas, usuario sin privilegios, healthcheck), `docker-compose.yml` con PostgreSQL 17 y volúmenes persistentes (`/data`: fotos, logs y clave del asistente), `docker/entrypoint.sh` (espera la base, migra y crea el superusuario inicial), `.dockerignore`, `.env.example` y la guía `docs/DESPLIEGUE_COOLIFY.md`. Endpoint `/healthz/`.
- Settings para servidor: `DATABASE_URL`, `BEHIND_HTTPS_PROXY`, `SERVIR_MEDIA`, `DATA_UPLOAD_MAX_MEMORY_SIZE_MB`, `DB_CONN_MAX_AGE`, y whitenoise cuando está instalado.
- Sistema bilingüe español / chino simplificado (中文). Cada usuario elige su idioma con el selector **ES / 中文** que aparece en mostrador, caja, recepción, elegir puesto, login, dashboard y panel central (y en la barra del admin); queda guardado en su perfil (`UserProfile.idioma`), así la misma PC muestra el idioma de quien inició sesión. Sin sesión se usa el último idioma elegido en esa PC y, si no hay, español. El gerente también puede fijarlo al crear el usuario en el admin.
- Traducción al chino de todas las pantallas del POS (HTML y JS), los mensajes de error de la API, los modelos y el admin, el dashboard financiero, el panel central y el inicio del admin. El asistente IA contesta en el idioma del usuario.
- Tests de idioma (`core/test_idioma.py`): preferencia por usuario, defecto en español, selector, y validación del catálogo chino (placeholders iguales y sin comillas que rompan el JS).

### Changed

- Los idiomas ofrecidos son solo español y chino (`settings.LANGUAGES`); los catálogos de inglés y portugués siguen en `locale/` pero no se ofrecen.
- Tickets impresos, PDF y Excel salen siempre en español (`pos.views._en_espanol`): el ticket lo recibe el cliente, las térmicas ESC/POS no suelen tener fuente china y los PDF usan Helvetica. El detalle de operación agrega `titulo_display` traducido para la pantalla y deja `titulo` en español para el ticket.
- `build_release.bat` compila las traducciones (`compilemessages`) antes de empaquetar.

### Fixed

- Tickets impresos: los acentos salían cambiados en térmicas con otra tabla de caracteres ("débito" → "d,bito"); ahora se imprimen sin acentos. El ticket de venta no mostraba la fecha (leía una clave que el detalle no manda) y en 58 mm el TOTAL se partía en dos renglones.
- La app de escritorio no mostraba ninguna foto (productos, remitos, visores): con DEBUG apagado `static()` no sirve nada. Ahora la ruta de media va a mano, como en el servidor Docker.
- El ejecutable de Windows no incluía los comandos de `manage.py` que importan modelos (PyInstaller los descartaba al no poder importarlos sin Django configurado); el spec ahora los suma leyendo las carpetas `management/commands`.

- `requirements.txt` estaba guardado en UTF-16 (pip y `makemessages` no lo leían bien en Linux); ahora es UTF-8, con versiones fijas y `gunicorn` + `whitenoise`.
- La central cortaba lotes de sincronización de más de 2,5 MB (remitos con fotos en base64); el límite ahora es configurable y en Docker es 100 MB.
- La central ya no arranca en producción con la `SECRET_KEY` de desarrollo.
- El nombre plural de `AdelantoCliente` en el admin era "Adelantos"; ahora es "Adelantos de clientes", como el resto de modelos (migración `ventas.0006`).

- Dashboard financiero para superadministradores (`/dash/`, app `dashboard`): cuatro paneles (ventas, compras, cuentas corrientes y gastos) con evolucion diaria, metricas comparadas contra el periodo anterior y top 10 de clientes, proveedores, saldos de cuenta corriente y gastos. Filtro por rango de fechas con presets, exportacion a PDF y Excel del lado del servidor. Los graficos se dibujan sobre canvas sin librerias externas, asi el panel funciona sin internet en la app de escritorio. Acceso restringido a `is_superuser`; el POS muestra el boton **Dash** solo a esos usuarios y el dashboard vuelve al POS.

### Changed

- El calculo de todas las metricas financieras se centralizo en `dashboard/services.py`, que ahora es la unica fuente de verdad: lo consumen tanto el dashboard del Django Admin (y sus exportaciones) como el dashboard nuevo, de modo que no pueden mostrar numeros distintos para lo mismo.

### Fixed

- Deuda de cliente en el dashboard del admin: las ventas con multipago sumaban el importe **completo** de la venta cuando el medio principal era cuenta corriente, en vez de solo la parte fiada. Ahora usa el mismo criterio que `Venta.monto_fiado` y que el estado de cuenta del cliente.
- KPI "Deuda proveedor emitida" del admin: sumaba **todas** las compras a proveedores, incluidas las pagadas al contado. Ahora cuenta solo las tomadas en cuenta corriente, que son las unicas que generan deuda (mismo criterio que `pos.views._proveedor_cc_data` y que el calculo de saldos).
- Asimetria entre clientes y proveedores: "Cobros de deuda" ignoraba los adelantos de cliente mientras que "Pagos a proveedores" si sumaba los adelantos a proveedor. Ahora ambas metricas incluyen los adelantos del periodo (los adelantos anulados siguen sin contar).

- Carga de categorias en el modal de venta: pad de ritmo rapido `categoria -> importe -> otra categoria -> importe`, con buscador por nombre (aparece con mas de 6 categorias), importe acumulado visible en cada categoria, sugerencia del importe restante y total calculado desde el desglose. El componente (`pos/templates/pos/_venta_categorias.html`) es compartido por el modal clasico y el guiado, y no se renderiza si no hay categorias cargadas.

## 0.0.1 - 2026-07-24

Version inicial del sistema bajo el nombre **Gestion de Carnicerias** (renombrado desde "SFI Minimalista"). Se limpio el historial de versiones previo y se dejaron unicamente las migraciones iniciales de cada app.

### Added

- Sistema de punto de venta (POS) con apertura/cierre de turnos de caja, ventas con uno o varios medios de pago, gastos, retiros de efectivo y pagos a proveedores.
- Gestion de clientes y proveedores con cuentas corrientes, adelantos y cancelaciones de deuda.
- Tesoreria centralizada: medios de pago, asignaciones por cajero y libro de movimientos de cuenta (`MovimientoCuenta`), con transferencias y ajustes manuales.
- Dashboard administrativo (Django Admin + Jazzmin) con metricas por rango de fechas y cajero, exportacion a Excel y PDF.
- Reportes PDF de cierre de turno y estado de cuenta de clientes/proveedores.
- Internacionalizacion (es/en/pt/zh-hans) via gettext.
- Empaquetado como aplicacion de escritorio para Windows (PyInstaller + NSIS).
