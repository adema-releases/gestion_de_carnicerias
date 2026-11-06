# Despliegue de la central en Coolify

La **central** (el frigorífico en la nube) corre en Docker. Las **sucursales** no: siguen con la app de escritorio de Windows (`build_release.bat`), que vende sin internet y sincroniza con la central cada minuto.

Archivos del despliegue:

| Archivo | Para qué |
| --- | --- |
| `Dockerfile` | Imagen de la central: Python 3.13, gunicorn, estáticos con whitenoise y traducciones compiladas. |
| `docker-compose.yml` | Central (`web`) + PostgreSQL 17 (`db`), con volúmenes persistentes y healthchecks. |
| `docker/entrypoint.sh` | Al arrancar: espera la base, corre `migrate` y crea el superusuario inicial si se pidió. |
| `.dockerignore` | Deja afuera `.env`, `venv/`, `media/`, logs y el build de Windows. |
| `.env.example` | Lista de variables. |

## 1. Antes de empezar

- El proyecto tiene que estar en un repositorio git (GitHub, GitLab o Gitea) al que Coolify tenga acceso. Nunca subas `.env` ni `agente_secret.key` (ya están en `.gitignore`).
- Un dominio o subdominio (por ejemplo `central.midominio.com`) apuntando con un registro A a la IP del servidor de Coolify.

## 2. Crear el recurso

1. En Coolify: **Projects → (tu proyecto) → + New → Resource**.
2. Elegí el repositorio (público, o privado con la GitHub App o deploy key) y la rama.
3. **Build Pack: Docker Compose**. Archivo: `/docker-compose.yml`.
4. Guardá. Coolify detecta los servicios `web` y `db`.

## 3. Variables de entorno

En **Environment Variables** cargá:

| Variable | Obligatoria | Valor |
| --- | --- | --- |
| `SECRET_KEY` | Sí | Una clave larga y aleatoria. Generala con `python -c "import secrets; print(secrets.token_urlsafe(50))"`. No la cambies después: invalida sesiones. |
| `POSTGRES_PASSWORD` | Sí | Contraseña de la base. |
| `ALLOWED_HOSTS` | Sí | El dominio sin `https://`: `central.midominio.com` |
| `CSRF_TRUSTED_ORIGINS` | Sí | El dominio con `https://`: `https://central.midominio.com` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | Primer deploy | Crea el usuario administrador si no existe. Después del primer ingreso podés borrarlas. |
| `POSTGRES_DB`, `POSTGRES_USER` | No | Por defecto `gestion_de_carnicerias` y `carnicerias`. |
| `GUNICORN_WORKERS` | No | Procesos web (por defecto 3). Regla: 2 × núcleos + 1. |
| `GUNICORN_TIMEOUT` | No | Segundos por pedido (por defecto 180). |
| `DATA_UPLOAD_MAX_MEMORY_SIZE_MB` | No | Tamaño máximo de un lote de sincronización (por defecto 100). Los remitos suben con fotos en base64. |

Ya vienen fijas en el compose: `SYNC_MODO=central`, `DEBUG=0`, `BEHIND_HTTPS_PROXY=1`, `SERVIR_MEDIA=1`, y la base apuntando al servicio `db`.

## 4. Dominio

En el servicio **web**, campo **Domains**: `https://central.midominio.com:8000`. El `:8000` le indica a Coolify el puerto del contenedor; el público queda en 443 con certificado de Let's Encrypt. El servicio **db** no lleva dominio: no se expone a internet.

## 5. Deploy y verificación

1. **Deploy**. El primer build tarda unos minutos.
2. En los logs de `web` tienen que aparecer `Base de datos lista`, las migraciones y `Booting worker`.
3. Abrí `https://central.midominio.com/healthz/`: tiene que decir `ok`.
4. Entrá a `https://central.midominio.com/admin/` con el superusuario y después al panel `/central/`.

## 6. Conectar las sucursales

Igual que en el [Manual de la central](MANUAL_CENTRAL.md#abrir-una-sucursal-nueva): creá la sucursal en el admin (genera el token) y en la PC de la sucursal poné en `C:\GestionDeCarnicerias\config.env`:

```env
SYNC_MODO=sucursal
SYNC_URL=https://central.midominio.com
SYNC_TOKEN=<token de la sucursal>
```

## 7. Datos y fotos que ya existen

Si ya tenés una central con datos (por ejemplo, la de prueba en una PC):

- **Base**: `pg_dump -Fc -d gestion_de_carnicerias -f central.dump` en el origen. Copialo al servidor y restauralo dentro del contenedor `db` con `pg_restore --clean --no-owner -U carnicerias -d gestion_de_carnicerias`. Hacelo antes de que las sucursales empiecen a sincronizar.
- **Fotos de productos**: van en el volumen `/data/media` del servicio `web` (por ejemplo `media/productos/`). Copialas con `docker cp media/. <contenedor-web>:/data/media/`.

## 8. Qué se guarda y dónde

| Volumen | Contenido | Backup |
| --- | --- | --- |
| `central_pg` | Base PostgreSQL | Diario con `pg_dump`. |
| `central_data` | `/data/media` (fotos), `/data/logs`, `/data/agente_secret.key` | Incluilo en el backup. Sin `agente_secret.key` no se puede descifrar la API key guardada del asistente IA. |

Los redeploys no borran los volúmenes. Borrar el recurso en Coolify sí puede borrarlos: hacé backup antes.

## 9. Alternativa: base de datos de Coolify

Si preferís la PostgreSQL administrada por Coolify (con backups desde la interfaz):

1. Creá un recurso **PostgreSQL** en el mismo proyecto y copiá su **Postgres URL (internal)**.
2. Creá la app con **Build Pack: Dockerfile** en vez de Docker Compose.
3. Variables: `DATABASE_URL=<la URL interna>`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` y, si querés, las `DJANGO_SUPERUSER_*`. `DATABASE_URL` tiene prioridad sobre las `DB_*`.
4. **Storage**: agregá un volumen persistente montado en `/data`.
5. Puerto expuesto: `8000`. Healthcheck: path `/healthz/`.

## 10. Arrancar con los datos de Frigorífico Uno

Para usar la nube directamente (vender desde el navegador) con Diana Catan ya cargada, agregá estas variables **antes del primer deploy**:

| Variable | Valor |
| --- | --- |
| `DATOS_INICIALES` | `frigorifico_uno` |
| `CLAVE_INICIAL_PERSONAL` | Clave inicial de `dueno`, `encargado`, `cajera1` y `vendedor1` (mínimo 8 caracteres). Cada uno la cambia después. |

En el primer arranque, con la base vacía, el contenedor corre `inicializar_nube`: medios de pago, Depósito Central Catan, Diana Catan, puestos, personal, el catálogo con códigos y las fotos (quedan en `/data/media`). En los redeploys no hace nada porque la base ya tiene datos. El log de `web` muestra `[inicializar_nube] Listo.`

`ADEMASISTEMAS` no queda con su clave de fábrica: si `DJANGO_SUPERUSER_USERNAME` es `ADEMASISTEMAS` toma `DJANGO_SUPERUSER_PASSWORD`; si no, queda sin clave y se entra con el superusuario de las variables.

Si la base ya tenía datos, el admin tiene *Usuario → Cargar datos de Frigorífico Uno*, que completa lo que falte sin pisar nada.

En la nube el servidor no ve las impresoras del local: los tickets no salen por la térmica directa (eso es de la app de escritorio de Windows).

## Problemas comunes

| Síntoma | Causa |
| --- | --- |
| `Bad Request (400)` | El dominio no está en `ALLOWED_HOSTS`. |
| `403 CSRF` al iniciar sesión | Falta el dominio con `https://` en `CSRF_TRUSTED_ORIGINS`. |
| El contenedor se reinicia y el log dice `necesita su propia SECRET_KEY` | Falta `SECRET_KEY`. La central no arranca con la clave de desarrollo. |
| Páginas sin estilos | El build no corrió `collectstatic`: revisá el log del build. |
| Las fotos no se ven | El volumen `/data` no está montado o falta `SERVIR_MEDIA=1`. |
| Una sucursal no sube remitos con fotos | Subí `DATA_UPLOAD_MAX_MEMORY_SIZE_MB` y `GUNICORN_TIMEOUT`. |
| `La base de datos no respondió` | El servicio `db` no levantó o la contraseña cambió después de crear el volumen (la de Postgres se fija en el primer arranque). |
