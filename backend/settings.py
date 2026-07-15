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


def env_int(name, default, minimum=None, maximum=None):
    value = os.environ.get(name)
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        raise RuntimeError(f"Configure {name} como numero inteiro.")
    if minimum is not None and parsed < minimum:
        raise RuntimeError(f"Configure {name} com valor >= {minimum}.")
    if maximum is not None and parsed > maximum:
        raise RuntimeError(f"Configure {name} com valor <= {maximum}.")
    return parsed


def unique_list(*groups):
    items = []
    for group in groups:
        for item in group or []:
            if item and item not in items:
                items.append(item)
    return items


DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").lower()
# Render.com seta automaticamente RENDER=true em todos os serviços deploy.
# Isso garante que IS_PRODUCTION funcione mesmo se DJANGO_ENV não for configurado manualmente.
_IS_RENDER = os.environ.get("RENDER", "").lower() in ("true", "1", "yes")
IS_PRODUCTION = DJANGO_ENV == "production" or _IS_RENDER

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-soluscrt-change-me-with-DJANGO_SECRET_KEY-before-production",
)
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
JWT_EXP_HOURS = env_int("JWT_EXP_HOURS", 12, minimum=1, maximum=168)

# Chave Fernet para cifrar embeddings biométricos em repouso (LGPD Art. 11).
# O placeholder abaixo NÃO é uma chave Fernet válida de propósito — só existe
# pra deixar claro (com erro imediato ao usar) que ninguém configurou a chave
# real via env var. Nunca usado em produção por causa do guard logo abaixo.
_BIOMETRIA_KEY_DEV = "dev-only-configure-BIOMETRIA_EMBEDDING_KEY-before-producao"
BIOMETRIA_EMBEDDING_KEY = os.environ.get("BIOMETRIA_EMBEDDING_KEY", _BIOMETRIA_KEY_DEV)

_CPF_KEY_DEV = "dev-cpf-nao-usar-em-producao-altere-via-CPF_ENCRYPTION_KEY"
CPF_ENCRYPTION_KEY = os.environ.get("CPF_ENCRYPTION_KEY", _CPF_KEY_DEV)

DEBUG = env_bool("DJANGO_DEBUG", default=not IS_PRODUCTION)
TRIAL_DAYS = env_int("TRIAL_DAYS", 15, minimum=1, maximum=90)
ALLOW_ENTERPRISE_DEMO_MUTATIONS = env_bool(
    "ALLOW_ENTERPRISE_DEMO_MUTATIONS",
    default=not IS_PRODUCTION,
)
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", default=False)
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
    or SECRET_KEY == JWT_SECRET_KEY
):
    raise RuntimeError(
        "Configure DJANGO_SECRET_KEY e JWT_SECRET_KEY longas e distintas antes de subir em produção."
    )

if IS_PRODUCTION and BIOMETRIA_EMBEDDING_KEY == _BIOMETRIA_KEY_DEV:
    raise RuntimeError(
        "Configure BIOMETRIA_EMBEDDING_KEY (chave Fernet própria) antes de subir em produção."
    )

if IS_PRODUCTION and CPF_ENCRYPTION_KEY == _CPF_KEY_DEV:
    raise RuntimeError(
        "Configure CPF_ENCRYPTION_KEY antes de subir em produção. "
        "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
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
] + (['django_extensions'] if not IS_PRODUCTION else [])

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
    'api.middleware.SegmentoAccessMiddleware',   # isolamento por segmento (SST/Farmácia/Hospital/Governo/Plano)
    'api.middleware.FetchAuthInterceptorMiddleware',
    'api.views_api_versioning.EnterpriseAPIMiddleware',
    'api.middleware.ContentSecurityPolicyMiddleware',
]

if not DEBUG:
    MIDDLEWARE.insert(
        MIDDLEWARE.index('django.middleware.security.SecurityMiddleware') + 1,
        'whitenoise.middleware.WhiteNoiseMiddleware',
    )

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", default=False)
SOLUSCRT_DEFAULT_ORIGINS = [
    "https://app-saude-p9n8.onrender.com",
    "https://soluscrt.com.br",
    "https://soluscrtsaude.com.br",
    "https://empresa.soluscrt.com.br",
    "https://governo.soluscrt.com.br",
    "https://admin.soluscrt.com.br",
    "https://app.soluscrt.com.br",
]
CORS_ALLOWED_ORIGINS = unique_list(
    env_list(
        "CORS_ALLOWED_ORIGINS",
        SOLUSCRT_DEFAULT_ORIGINS if IS_PRODUCTION else [],
    ),
    SOLUSCRT_DEFAULT_ORIGINS if IS_PRODUCTION else [],
)
if IS_PRODUCTION and CORS_ALLOW_ALL_ORIGINS:
    raise RuntimeError("CORS_ALLOW_ALL_ORIGINS deve ser false em producao.")

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
                'api.context_processors.profile_navigation',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# APP_DATABASE_URL  → usuário restrito soluscrt_app (sujeito ao RLS, para queries da app)
# DATABASE_URL      → usuário superuser / dono do banco (bypassa RLS, usado em migrations
#                     e cron jobs que não passam pelo EmpresaMiddleware)
#
# Se APP_DATABASE_URL não estiver definida (cron jobs, preDeployCommand com override),
# o Django usa DATABASE_URL normalmente — sem quebrar nada.
_APP_DB_URL = os.environ.get("APP_DATABASE_URL") or ""
_OWNER_DB_URL = os.environ.get("DATABASE_URL") or ""
DATABASE_URL = _APP_DB_URL or _OWNER_DB_URL

if DATABASE_URL:
    import dj_database_url

    default_database = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=IS_PRODUCTION,
    )
    if IS_PRODUCTION and default_database.get("ENGINE") == "django.db.backends.sqlite3":
        raise RuntimeError("DATABASE_URL de producao deve apontar para PostgreSQL gerenciado, nao SQLite.")
    DATABASES = {
        "default": default_database
    }

    # Conexão "owner" — usa DATABASE_URL (papel dono do banco, que BYPASSA o RLS).
    # Necessária para lookups cross-tenant que acontecem ANTES de sabermos o
    # empresa_id (ex.: login do app do funcionário, que resolve a credencial pelo
    # e-mail antes de ter qualquer contexto de tenant). A conexão "default" usa o
    # papel restrito soluscrt_app e, sob RLS sem app.empresa_id setado, não enxerga
    # nenhuma linha — por isso o login do portal precisa do papel owner.
    if _OWNER_DB_URL and _OWNER_DB_URL != _APP_DB_URL:
        DATABASES["owner"] = dj_database_url.parse(
            _OWNER_DB_URL,
            conn_max_age=600,
            ssl_require=IS_PRODUCTION,
        )
    else:
        # Sem URL de owner distinta (dev, ou APP_DATABASE_URL ausente): o alias
        # "owner" aponta para a mesma config da default — sem RLS a contornar.
        DATABASES["owner"] = dict(default_database)
    # Em testes, "owner" usa o mesmo banco de teste que "default" para que dados
    # criados via default sejam visíveis em queries .using("owner") (sem RLS em testes).
    DATABASES["owner"]["TEST"] = {"MIRROR": "default"}
else:
    if IS_PRODUCTION:
        raise RuntimeError("Configure DATABASE_URL com PostgreSQL gerenciado antes de subir em producao.")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    # SQLite não tem RLS; o alias "owner" espelha a default só para que
    # `.using("owner")` funcione igual em dev e em produção.
    DATABASES["owner"] = dict(DATABASES["default"])
    DATABASES["owner"]["TEST"] = {"MIRROR": "default"}

# ── Multi-tenant RLS ──────────────────────────────────────────────────────────
# Envolve cada requisição HTTP em uma única transação PostgreSQL.
# Isso garante que o SET LOCAL app.empresa_id (definido no EmpresaMiddleware)
# fique ativo durante toda a request e seja limpo automaticamente no COMMIT,
# sem risco de vazar entre conexões reutilizadas (conn_max_age=600).
ATOMIC_REQUESTS = True

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Mídia (arquivos enviados pelo usuário, ex. DICOM do RIS/PACS) ────────────
# Em produção (Render), MEDIA_ROOT_OVERRIDE aponta para o disco persistente
# montado via render.yaml — arquivos sobrevivem a redeploys. Sem essa env var
# (dev local), cai no filesystem local em BASE_DIR/mediafiles (não persiste
# entre deploys, mas funciona para desenvolvimento e teste).
MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT_OVERRIDE") or (BASE_DIR / "mediafiles")
# Importante: MEDIA_URL não é servido publicamente em nenhuma urlpattern —
# arquivos DICOM/laudos são clínicos/sensíveis e só devem ser acessados via
# view autenticada (ver api_ris_dicom_arquivo, api_resultado_arquivo), nunca
# por URL estática direta.

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',

    
    ]
}

_REDIS_URL = os.environ.get("REDIS_URL", "")
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 3,
                "SOCKET_TIMEOUT": 3,
                "IGNORE_EXCEPTIONS": True,
            },
        }
    }
elif IS_PRODUCTION:
    raise RuntimeError(
        "Configure REDIS_URL em produção. Sem Redis o rate limiting de login "
        "não funciona entre workers e o cache é perdido a cada restart."
    )
else:
    # Dev local: FileBasedCache compartilhado entre workers Gunicorn via filesystem.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": "/tmp/django_cache",
        }
    }

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if not IS_PRODUCTION else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.zoho.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "SolusCRT <admin@soluscrt.com.br>")

PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "" if IS_PRODUCTION else "http://127.0.0.1:8000",
).rstrip("/")
if IS_PRODUCTION and not PUBLIC_BASE_URL:
    raise RuntimeError(
        "Configure PUBLIC_BASE_URL com a URL publica do servidor antes de subir em producao. "
        "Exemplo: PUBLIC_BASE_URL=https://app.soluscrt.com.br"
    )

ASAAS_API_KEY = (os.environ.get("ASAAS_API_KEY", "") or "").strip()
ASAAS_BASE_URL = (os.environ.get("ASAAS_BASE_URL", "https://api.asaas.com/v3") or "").strip().rstrip("/")
ASAAS_WEBHOOK_TOKEN = (os.environ.get("ASAAS_WEBHOOK_TOKEN", "") or "").strip()

# ── Jitsi Meet / JaaS (8x8.vc) ───────────────────────────────────────────────
# Dev: deixe JITSI_APP_ID e JITSI_KID vazios → usa meet.jit.si público sem JWT
# Prod (JaaS): defina JITSI_APP_ID, JITSI_KID e JITSI_PRIVATE_KEY_PATH (ou _B64)
JITSI_DOMAIN = os.environ.get("JITSI_DOMAIN", "meet.jit.si")
JITSI_APP_ID = os.environ.get("JITSI_APP_ID", "")
JITSI_KID = os.environ.get("JITSI_KID", "")
JITSI_PRIVATE_KEY_PATH = os.environ.get("JITSI_PRIVATE_KEY_PATH", "")  # caminho do .pk
JITSI_PRIVATE_KEY_B64 = os.environ.get("JITSI_PRIVATE_KEY_B64", "")   # alternativa base64
JITSI_SECRET = os.environ.get("JITSI_SECRET", "")  # legado HS256 — não usado com JaaS
if IS_PRODUCTION and not ASAAS_WEBHOOK_TOKEN:
    raise RuntimeError("Configure ASAAS_WEBHOOK_TOKEN em producao para validar webhooks de pagamento.")
ASAAS_USER_AGENT = (os.environ.get("ASAAS_USER_AGENT", "SolusCRT-Saude/1.0") or "SolusCRT-Saude/1.0").strip()
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
CSRF_COOKIE_HTTPONLY = False  # must be False so JS can read the token for AJAX POSTs
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=IS_PRODUCTION)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=IS_PRODUCTION)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "SAMEORIGIN"

# ── Email — aviso quando SMTP não está configurado em produção ───────────────

# ── Sentry — monitoramento de erros em produção ──────────────────────────────
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            LoggingIntegration(level=None, event_level="ERROR"),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.05,
        send_default_pii=False,
        environment=DJANGO_ENV,
        release=os.environ.get("RENDER_GIT_COMMIT", "local"),
    )
