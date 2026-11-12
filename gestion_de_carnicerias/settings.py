from pathlib import Path
from dotenv import load_dotenv
import os
import time
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga el archivo .env
load_dotenv(os.path.join(BASE_DIR, '.env'))

def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(',') if item.strip()]


# Sincronización: 'sucursal' (PC local) o 'central' (la nube)
SYNC_MODO = os.getenv('SYNC_MODO', 'sucursal')
SYNC_URL = os.getenv('SYNC_URL', '').rstrip('/')
SYNC_TOKEN = os.getenv('SYNC_TOKEN', '')

_SECRET_KEY_DESARROLLO = 'django-insecure-gestion-de-carnicerias-local-development-key'
SECRET_KEY = os.getenv('SECRET_KEY', _SECRET_KEY_DESARROLLO)
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://127.0.0.1:8250,http://localhost:8250')

if SYNC_MODO == 'central' and not DEBUG and SECRET_KEY == _SECRET_KEY_DESARROLLO:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('La central en producción necesita su propia SECRET_KEY (variable de entorno).')

# El healthcheck del contenedor llama a 127.0.0.1: siempre tiene que estar permitido.
if '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS += [h for h in ('localhost', '127.0.0.1') if h not in ALLOWED_HOSTS]

# Detrás del proxy HTTPS de Coolify (Traefik/Caddy): Django ve HTTP y el proxy
# avisa con X-Forwarded-Proto que el pedido original era HTTPS.
if env_bool('BEHIND_HTTPS_PROXY', False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

if os.environ.get('GESTION_CARNICERIAS_DESKTOP') == '1':
    ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*')
    CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://127.0.0.1:8250,http://localhost:8250')

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'import_export',
    'core',
    'tesoreria',
    'inventario',
    'compras',
    'ventas',
    'gastos',
    'recepcion',
    'central',
    'pos',
    'dashboard',
    'agente',
    'ayuda',  # Guía rápida: buscador de tutoriales en español y chino (F1)
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.UserLanguageMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'gestion_de_carnicerias.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'gestion_de_carnicerias.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'gestion_de_carnicerias'),
        'USER': os.environ.get('DB_USER', 'kevin'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        # Reusa conexiones entre pedidos (gunicorn); 0 = una por pedido, como antes.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '0')),
    }
}

# Coolify (y otros PaaS) entregan la base como una URL:
# postgres://usuario:clave@host:5432/base  — si está, tiene prioridad sobre DB_*.
if os.environ.get('DATABASE_URL'):
    from urllib.parse import unquote, urlsplit

    _db = urlsplit(os.environ['DATABASE_URL'])
    DATABASES['default'].update({
        'NAME': unquote(_db.path.lstrip('/')),
        'USER': unquote(_db.username or ''),
        'PASSWORD': unquote(_db.password or ''),
        'HOST': _db.hostname or '',
        'PORT': str(_db.port or 5432),
    })


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'es'

# El sistema se ve en español (por defecto) o en chino simplificado. Cada
# usuario elige el suyo (UserProfile.idioma) y lo aplica UserLanguageMiddleware.
# Los catálogos de inglés y portugués siguen en locale/ pero no se ofrecen.
LANGUAGES = [
    ('es', _('Spanish')),
    ('zh-hans', _('Chinese')),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

TIME_ZONE = 'America/Argentina/Buenos_Aires'
os.environ['TZ'] = TIME_ZONE
if hasattr(time, 'tzset'):
    time.tzset()

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL          = '/static/'
STATIC_ROOT         = BASE_DIR / 'staticfiles'
STATICFILES_DIRS    = [BASE_DIR / 'static']

MEDIA_URL           = '/media/'
MEDIA_ROOT          = os.environ.get('MEDIA_ROOT', BASE_DIR / 'media')

# Con whitenoise instalado (servidor/Docker), Django sirve los estáticos sin
# depender de DEBUG. La app de escritorio no lo trae y sigue como antes.
try:
    import whitenoise  # noqa: F401
except ImportError:
    pass
else:
    MIDDLEWARE.insert(MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
                      'whitenoise.middleware.WhiteNoiseMiddleware')
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        # Sin "Manifest": un {% static %} a un archivo inexistente no rompe la página.
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
    }

# La central recibe lotes de sincronización con fotos en base64 (remitos, visores):
# el límite de Django (2,5 MB) los cortaría. En la central se sube por variable de entorno.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(float(os.environ.get('DATA_UPLOAD_MAX_MEMORY_SIZE_MB', '2.5')) * 1024 * 1024)

LOG_DIR = Path(os.environ.get('LOG_DIR', BASE_DIR / 'logs'))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'gestion_de_carnicerias.log',
            'formatter': 'standard',
            'encoding': 'utf-8',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['file', 'console'],
        'level': 'INFO',
    },
}

DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
LOGIN_URL          = '/accounts/login/'
LOGIN_REDIRECT_URL = '/pos/'
LOGOUT_REDIRECT_URL = '/pos/'


# Nombre del proyecto para mostrar en el admin
PROJECT_TITLE = _("Gestion de Carnicerias")


JAZZMIN_SETTINGS = {

    
    # Títulos principales
    "site_title": PROJECT_TITLE,        # Ventana del navegador
    "site_header": PROJECT_TITLE,       # Encabezado superior
    "site_brand": PROJECT_TITLE,        # Nombre de la marca en el sidebar

    # Logos (deben existir en STATICFILES)
    "site_logo": "img/logo.png",  # Logo pequeño en la esquina
    "login_logo": "img/logo.png", # Logo en la pantalla de login
    "site_logo_classes": "img-rectangle",  # Clases CSS para el logo (ajusta según tu imagen)

    # Oculta toda la app
    "hide_apps":   ["core","auth"],

    # Ocultar modelos específicos
    "hide_models": [
        "auth.group",
        "auth.user",
        "core.configuracion",

        "compras.cancelaciondeudaproveedor",

        "inventario.categoria",

        "gastos.categoriagasto",
    ],

    # Orden de las apps/modelos en el sidebar
    "order_with_respect_to": [
        "ventas", 
        "ventas.venta", 
        "ventas.cliente",   
        "compras",
        "gastos", 
        "tesoreria", 
        "inventario"
        ],

    "topmenu_links": [
        {
            "name": _("Ir al POS"),
            "url": "/pos/",
            "icon": "fas fa-cash-register",
            "permissions": [],
        },
        # Dropdown de Core
        {
            "name":       _("Core"),
            "app":        "core",   # agrupa todas las urls de core
            "permissions": [],      # (opcional) podrías restringir con permisos
        },
        {
            "name": _("Inventory"),
            "app":  "inventario",   # agrupa todas las urls de la app inventario
            "permissions": [],      # (opcional) podrías restringir con permisos
        },
        {
            "name":       _("Purchases"),
            "app":        "compras",   # agrupa todas las urls de core
            "permissions": [],      # (opcional) podrías restringir con permisos
        },
        {
            "name": _("Sales"),
            "app":  "ventas",   # agrupa todas las urls de la app inventario
            "permissions": [],      # (opcional) podrías restringir con permisos
        },
        {
            "name": _("Expenses"),
            "app":  "gastos",   # agrupa todas las urls de la app gastos
            "permissions": [],      # (opcional) podrías restringir con permisos
        },
        {
            "name": _("Treasury"),
            "app":  "tesoreria",
            "permissions": [],
        }
    ],

    "usermenu_links": [
        {
            "name": _("Ir al POS"),
            "url": "/pos/",
            "icon": "fas fa-cash-register",
            "permissions": [],
        },
        {
            "name": _("Cargar datos de Frigorífico Uno"),
            "url": "/admin/system/frigorifico-uno/",
            "icon": "fas fa-download",
            "permissions": ["auth.view_user"],
        },
        {
            "name": _("Respaldo de la base"),
            "url": "/admin/system/respaldo/",
            "icon": "fas fa-file-archive",
            "permissions": ["auth.view_user"],
        },
        {
            "name": _("Resetear de fabrica"),
            "url": "/admin/system/factory-reset/",
            "icon": "fas fa-power-off",
            "permissions": ["auth.view_user"],
        }
    ],

    # Texto de bienvenida y pie de página
    "welcome_sign": format_lazy(_("Welcome to {project_title}"), project_title=PROJECT_TITLE),
    "copyright": PROJECT_TITLE,
    "custom_js": "js/admin-factory-reset.js",
    # Selector Español / 中文 en la barra superior (guarda el idioma en el perfil).
    "language_chooser": True,

    # Menú lateral
    "show_sidebar": True,
    "navigation_expanded": False,
    "show_ui_builder": True,  # Oculta el enlace al UI Builder

    # Íconos básicos (FontAwesome)
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.group": "fas fa-users",

        "core": "fas fa-screwdriver-wrench",
        "core.configuracion": "fas fa-cogs",
        "core.userprofile": "fas fa-id-badge",
        "core.permisoscajero": "fas fa-user-lock",

        "ventas": "fas fa-cash-register",
        "ventas.adelantocliente": "fas fa-sack-dollar",
        "ventas.cliente": "fas fa-user-tag",
        "ventas.cobrodeuda": "fas fa-hand-holding-dollar",
        "ventas.cobrodeudaadelantodetalle": "fas fa-link",
        "ventas.cobrodeudadetalle": "fas fa-list-check",
        "ventas.cobrodeudasaldoinicialdetalle": "fas fa-clipboard-list",
        "ventas.retiroefectivo": "fas fa-money-bill-transfer",
        "ventas.saldoinicialcliente": "fas fa-circle-dollar-to-slot",
        "ventas.turnocaja": "fas fa-box-archive",
        "ventas.venta": "fas fa-receipt",
        "ventas.ventapago": "fas fa-credit-card",

        "compras": "fas fa-truck-field",
        "compras.cancelaciondeudaproveedor": "fas fa-clipboard-check",
        "compras.cancelaciondeudaproveedordetalle": "fas fa-list-check",
        "compras.cancelaciondeudaproveedorsaldoinicialdetalle": "fas fa-clipboard-list",
        "compras.pagoproveedor": "fas fa-file-invoice-dollar",
        "compras.proveedor": "fas fa-truck",
        "compras.saldoinicialproveedor": "fas fa-scale-balanced",

        "gastos": "fas fa-wallet",
        "gastos.categoriagasto": "fas fa-folder-tree",
        "gastos.gasto": "fas fa-file-invoice",

        "tesoreria": "fas fa-vault",
        "tesoreria.asignacionmediopagocajero": "fas fa-user-shield",
        "tesoreria.mediodepago": "fas fa-credit-card",
        "tesoreria.movimientocuenta": "fas fa-arrow-right-arrow-left",
        "tesoreria.ajustecuenta": "fas fa-cog",
        "inventario": "fas fa-tags",
        "inventario.categoria": "fas fa-tag",

    },

    # Apariencia del formulario de cambio
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": False,
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "darkly",
    "dark_mode_theme": None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": True
}
