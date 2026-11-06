---
titulo: Operación y mantenimiento
seo_title: Operación: instalación, sincronización, impresora y base
seo_description: Guía para quien instala y mantiene el sistema: PC de la sucursal, tablets, sincronización con la central, impresora y cajón, y base de datos.
palabras_clave: [instalar sistema carnicería, sincronización, impresora de tickets, config.env]
rol: soporte
modulo: instalación, sincronización, impresión
permiso: superusuario
estado: verificado
verificado: 2026-11-03 contra run_server.py, postgres_local.py, installer.nsi, core/agente_sync.py, pos/printing.py y README.md
version_sistema: 0.0.1
---

# Operación y mantenimiento

> **Para quién es:** quien instala y mantiene el sistema. **No hace falta para el día a día.** El detalle técnico completo está en el [README del proyecto](../../../README.md).

## La PC de la sucursal

- El instalador de Windows trae su propio **PostgreSQL**: no hace falta instalar nada aparte.
- La primera vez crea la base en `C:\GestionDeCarnicerias\pgdata` (puerto local 5433) y la deja lista.
- La app arranca al iniciar sesión y se maneja desde el **ícono de la bandeja**. Al salir, apaga la base.
- La configuración está en `C:\GestionDeCarnicerias\config.env`:

  ```env
  SYNC_MODO=sucursal
  SYNC_URL=https://<dirección de la central>
  SYNC_TOKEN=<token de la sucursal>
  ```

## Tablets y celulares

- Se conectan al **wifi de la carnicería** y abren `http://<IP de la PC>:8250/pos/`.
- El instalador abre el puerto 8250 en el firewall de Windows.
- La IP de la PC queda anotada en el registro de la app cuando arranca. Conviene fijarla en el router.

## Sincronización

- Cada 60 segundos, si hay `SYNC_URL` y `SYNC_TOKEN`, la PC sube sus cambios y baja los de la central.
- Sin internet la sucursal sigue vendiendo; los cambios esperan en una cola.
- A mano: `python manage.py sincronizar` · `--inicial` (una sucursal que ya tenía datos) · `--catalogo` (subir el catálogo a una central vacía) · `--loop 60`.
- El frigorífico ve la última sincronización de cada sucursal en el [panel central](../01-manual-usuario/23-panel-central.md).

## Impresora de tickets y cajón

- Cargá el nombre exacto de la impresora en la caja (**Configurar impresora**) o en *Configuración → POS — General*.
- El cajón monedero se abre solo cuando una venta incluye **efectivo**. Requiere `pywin32`.
- Si no hay impresora, la venta se registra igual.

## Base de datos y respaldo

- PostgreSQL, en la sucursal y en la central.
- Para respaldar la PC de la sucursal, copiá la base con `pg_dump` (puerto 5433, usuario `carnicerias`, clave en `C:\GestionDeCarnicerias\db\clave_postgres.txt`).
- Si una versión nueva trae otra versión mayor de PostgreSQL, la app no arranca con los datos viejos hasta correr `pg_upgrade`.

## Idiomas

- Español y chino. Para actualizar traducciones ver la sección *Internacionalización* del [README del proyecto](../../../README.md).
