# Imagen de la CENTRAL (frigorífico en la nube) para Docker / Coolify.
# Las sucursales siguen usando la app de escritorio de Windows (build_release.bat).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Argentina/Buenos_Aires

# gettext: compilar las traducciones (español / chino). curl: healthcheck de Coolify.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext curl tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Estáticos y traducciones se generan en la imagen. La SECRET_KEY de acá solo
# sirve para que Django cargue; la real llega por variable de entorno.
RUN SECRET_KEY=build-only SYNC_MODO=sucursal python manage.py collectstatic --noinput \
    && SECRET_KEY=build-only SYNC_MODO=sucursal python manage.py compilemessages -l es -l zh_Hans \
    && sed -i 's/\r$//' docker/entrypoint.sh \
    && chmod +x docker/entrypoint.sh

# Usuario sin privilegios. /data es el volumen persistente: fotos (media),
# logs y la clave de cifrado del asistente (agente_secret.key).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/media /data/logs \
    && chown -R app:app /data /app
USER app

ENV SYNC_MODO=central \
    MEDIA_ROOT=/data/media \
    LOG_DIR=/data/logs \
    SERVIR_MEDIA=1 \
    BEHIND_HTTPS_PROXY=1 \
    DATA_UPLOAD_MAX_MEMORY_SIZE_MB=100 \
    DB_CONN_MAX_AGE=60 \
    PORT=8000

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/healthz/" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
# Timeout alto: los lotes de sincronización pueden traer fotos.
CMD ["sh", "-c", "exec gunicorn gestion_de_carnicerias.wsgi:application --bind 0.0.0.0:${PORT} --workers ${GUNICORN_WORKERS:-3} --timeout ${GUNICORN_TIMEOUT:-180} --forwarded-allow-ips='*' --access-logfile - --error-logfile -"]
