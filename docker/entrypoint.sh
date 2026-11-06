#!/bin/sh
# Arranque del contenedor de la central: espera la base, migra y (opcional)
# crea el superusuario inicial. Después ejecuta el comando (gunicorn).
set -e

echo "[entrypoint] Esperando la base de datos..."
python - <<'PY'
import os, sys, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_de_carnicerias.settings')
import django
django.setup()
from django.db import connection
for intento in range(60):
    try:
        connection.ensure_connection()
        print('[entrypoint] Base de datos lista.')
        break
    except Exception as exc:  # noqa: BLE001
        print(f'[entrypoint] Base no disponible ({exc.__class__.__name__}), reintento {intento + 1}/60')
        time.sleep(2)
else:
    sys.exit('[entrypoint] La base de datos no respondió en 2 minutos.')
PY

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] Aplicando migraciones..."
    python manage.py migrate --noinput
fi

# Superusuario inicial: solo si se definen las variables y todavía no existe.
if [ -n "${DJANGO_SUPERUSER_USERNAME}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then
    python - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_de_carnicerias.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
if User.objects.filter(username=username).exists():
    print(f'[entrypoint] El superusuario {username} ya existe.')
else:
    User.objects.create_superuser(
        username=username,
        email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
        password=os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
    print(f'[entrypoint] Superusuario {username} creado.')
PY
fi

# Datos iniciales (ej: DATOS_INICIALES=frigorifico_uno): solo cargan con la base vacía,
# o sea en el primer deploy. Si fallan, la app arranca igual y el log dice por qué.
if [ -n "${DATOS_INICIALES}" ]; then
    python manage.py inicializar_nube || echo "[entrypoint] No se pudieron cargar los datos iniciales (ver arriba)."
fi

exec "$@"
