import os
import sys
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

DEBUG = _env_bool("DEBUG", False)
TESTING = "test" in sys.argv

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-change-in-production"
    else:
        raise ImproperlyConfigured("SECRET_KEY ausente em produção")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY).strip()

ALLOWED_HOSTS = _env_list(
    "ALLOWED_HOSTS",
    ",".join(
        [
            "localhost",
            "127.0.0.1",
            "empresa.soluscrt.com.br",
            "governo.soluscrt.com.br",
            "admin.soluscrt.com.br",
            "app.soluscrt.com.br",
            "soluscrt.com.br",
            "www.soluscrt.com.br",
            "app-saude-p9n8.onrender.com",
        ]
    ),
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

CORS_ALLOW_ALL_ORIGINS = _env_bool("CORS_ALLOW_ALL_ORIGINS", False)
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = _env_list(
        "CORS_ALLOWED_ORIGINS",
        ",".join(
            [
                "https://empresa.soluscrt.com.br",
                "https://governo.soluscrt.com.br",
                "https://admin.soluscrt.com.br",
                "https://app.soluscrt.com.br",
                "https://soluscrt.com.br",
                "https://www.soluscrt.com.br",
                "https://app-saude-p9n8.onrender.com",
            ]
        ),
    )

CSRF_TRUSTED_ORIGINS = _env_list(
    "CSRF_TRUSTED_ORIGINS",
    ",".join(
        [
            "https://empresa.soluscrt.com.br",
            "https://governo.soluscrt.com.br",
            "https://admin.soluscrt.com.br",
            "https://app.soluscrt.com.br",
            "https://soluscrt.com.br",
            "https://www.soluscrt.com.br",
            "https://app-saude-p9n8.onrender.com",
        ]
    ),
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", not DEBUG and not TESTING)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

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
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Pagamentos
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "asaas").strip().lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://app-saude-p9n8.onrender.com").rstrip("/")

MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN", "")
MERCADO_PAGO_WEBHOOK_SECRET = os.getenv("MERCADO_PAGO_WEBHOOK_SECRET", "")

ASAAS_API_KEY = os.getenv("ASAAS_API_KEY", "")
ASAAS_BASE_URL = os.getenv("ASAAS_BASE_URL", "https://api.asaas.com/v3").rstrip("/")
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "")
ASAAS_USER_AGENT = os.getenv("ASAAS_USER_AGENT", "SolusCRT-Saude/1.0")

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
