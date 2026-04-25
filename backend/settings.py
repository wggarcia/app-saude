from pathlib import Path
import os
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def unique_list(*groups):
    items = []
    for group in groups:
        for item in group or []:
            if item and item not in items:
                items.append(item)
    return items


DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").lower()
IS_PRODUCTION = DJANGO_ENV == "production"

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-soluscrt-change-me-with-DJANGO_SECRET_KEY-before-production",
)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)

DEBUG = env_bool("DJANGO_DEBUG", default=not IS_PRODUCTION)
SOLUSCRT_DEFAULT_HOSTS = [
    "127.0.0.1",
    "localhost",
    "testserver",
    "app-saude-p9n8.onrender.com",
    "soluscrt.com.br",
    "soluscrtsaude.com.br",
    "empresa.soluscrt.com.br",
    "governo.soluscrt.com.br",
    "admin.soluscrt.com.br",
    "app.soluscrt.com.br",
    ".soluscrt.com.br",
    ".soluscrtsaude.com.br",
]
ALLOWED_HOSTS = unique_list(
    env_list(
        "DJANGO_ALLOWED_HOSTS",
        SOLUSCRT_DEFAULT_HOSTS,
    ),
    SOLUSCRT_DEFAULT_HOSTS,
)

if IS_PRODUCTION and (
    SECRET_KEY.startswith("dev-only-")
    or JWT_SECRET_KEY.startswith("dev-only-")
    or len(SECRET_KEY) < 50
    or len(JWT_SECRET_KEY) < 50
):
    raise RuntimeError(
        "Configure DJANGO_SECRET_KEY e JWT_SECRET_KEY longas antes de subir em produção."
    )


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'api',
    'corsheaders',
    'django_extensions',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.EmpresaMiddleware',
]

if not DEBUG:
    MIDDLEWARE.insert(
        MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
        'whitenoise.middleware.WhiteNoiseMiddleware',
    )

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", default=not IS_PRODUCTION)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
SOLUSCRT_DEFAULT_ORIGINS = [
    "https://app-saude-p9n8.onrender.com",
    "https://soluscrt.com.br",
    "https://soluscrtsaude.com.br",
    "https://empresa.soluscrt.com.br",
    "https://governo.soluscrt.com.br",
    "https://admin.soluscrt.com.br",
    "https://app.soluscrt.com.br",
]
CSRF_TRUSTED_ORIGINS = unique_list(
    env_list(
        "CSRF_TRUSTED_ORIGINS",
        SOLUSCRT_DEFAULT_ORIGINS if IS_PRODUCTION else [],
    ),
    SOLUSCRT_DEFAULT_ORIGINS if IS_PRODUCTION else [],
)

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'api.context_processors.public_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=IS_PRODUCTION,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',

    
    ]
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://app-saude-p9n8.onrender.com" if IS_PRODUCTION else "http://127.0.0.1:8000",
).rstrip("/")

PAYMENT_PROVIDER = (os.environ.get("PAYMENT_PROVIDER", "mercado_pago") or "mercado_pago").strip().lower()
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN", "")
MERCADO_PAGO_WEBHOOK_SECRET = os.environ.get("MERCADO_PAGO_WEBHOOK_SECRET", "")
ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY", "")
ASAAS_BASE_URL = (os.environ.get("ASAAS_BASE_URL", "https://api.asaas.com/v3") or "").strip().rstrip("/")
ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")
ASAAS_USER_AGENT = os.environ.get("ASAAS_USER_AGENT", "SolusCRT-Saude/1.0")
FIREBASE_SERVICE_ACCOUNT_PATH = os.environ.get(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    str(BASE_DIR / "secrets" / "firebase-service-account.json"),
)
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "")
GOOGLE_MAPS_BROWSER_KEY = os.environ.get("GOOGLE_MAPS_BROWSER_KEY", "")
GOOGLE_MAPS_IOS_KEY = os.environ.get("GOOGLE_MAPS_IOS_KEY", "")

SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=IS_PRODUCTION)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=IS_PRODUCTION)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
