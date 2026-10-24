from pathlib import Path

import dj_database_url

from config.env import env, env_bool, env_duration, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env("SECRET_KEY", required=True)
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # tiers
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    # projet
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.media",
    "apps.competition",
    "apps.categories",
    "apps.candidates",
    "apps.news",
    "apps.team",
    "apps.partners",
    "apps.advertising",
    "apps.voting",
    "apps.payments",
    "apps.ticketing",
    "apps.finance",
    "apps.publicapi",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Base de données / cache
# --------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", required=True), conn_max_age=60, conn_health_checks=True
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Mots de passe
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Fichiers statiques et médias
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", str(BASE_DIR / "staticfiles"))
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", str(BASE_DIR / "media"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --------------------------------------------------------------------------
# CORS / CSRF (jamais de "autoriser tout" : origines explicites par variable)
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# --------------------------------------------------------------------------
# Proxy / IP client
# --------------------------------------------------------------------------
# Nombre de reverse-proxies de confiance devant l'application (0 = aucun).
NUM_PROXIES = env_int("NUM_PROXIES", 0)

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.AdminJWTAuthentication"],
    # Refus par défaut : chaque vue doit déclarer explicitement ses permissions.
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.permissions.DenyByDefault"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "1000/min",
        "login": "10/min",
        "refresh": "60/min",
        "webhook": "300/min",
        "vote_order": "20/min",
    },
    "NUM_PROXIES": NUM_PROXIES,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "African Talents API",
    "DESCRIPTION": (
        "API du site public et de l'espace administrateur African Talents.\n\n"
        "- Les routes sous `/public/` ne nécessitent aucune authentification.\n"
        "- Toutes les autres routes exigent un jeton `Bearer` obtenu via `/auth/login/`.\n"
        "- Format d'erreur unique : `{\"success\": false, \"message\": \"...\", \"code\": \"...\"}`.\n"
        "- Le prix d'un vote est toujours défini par l'administrateur (forfaits `/vote-packages/`), "
        "jamais par le client qui passe une commande."
    ),
    "VERSION": "1.0.0",
    "CONTACT": {"name": "African Talents — équipe technique"},
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "SORT_OPERATIONS": False,
    "TAGS": [
        {"name": "auth", "description": "Connexion, rafraîchissement de session, profil courant."},
        {"name": "admins", "description": "Gestion des comptes administrateurs."},
        {"name": "roles", "description": "Rôles et permissions (RBAC)."},
        {"name": "audit-logs", "description": "Journal d'activité (lecture seule, en ajout seul côté serveur)."},
        {"name": "competitions", "description": "Compétition et ses phases."},
        {"name": "categories", "description": "Catégories de la compétition."},
        {"name": "candidates", "description": "Candidats."},
        {"name": "news", "description": "Actualités (mini-CMS)."},
        {"name": "team", "description": "Équipe et coachs."},
        {"name": "media", "description": "Médiathèque."},
        {"name": "vote-packages", "description": "Forfaits de vote définis par l'administrateur (quantité + prix)."},
        {"name": "votes", "description": "Grand livre des votes, ajustements manuels, statistiques."},
        {"name": "rankings", "description": "Classement (agrégation du grand livre des votes)."},
        {"name": "payments", "description": "Paiements et webhook HR-Skills Pay."},
        {"name": "ticketing", "description": "Tarifs, commandes, billets et statistiques de billetterie."},
        {"name": "finance", "description": "Vue d'ensemble, compte marchand, rapprochement, rapports."},
        {"name": "settings", "description": "Paramètres généraux du site (singleton)."},
        {"name": "public", "description": "API publique sans authentification, consommée par le site public."},
    ],
}

# --------------------------------------------------------------------------
# JWT + cookie de refresh
# --------------------------------------------------------------------------
JWT_ACCESS_LIFETIME = env_duration("JWT_ACCESS_LIFETIME", "15m")
JWT_REFRESH_LIFETIME = env_duration("JWT_REFRESH_LIFETIME", "7d")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": JWT_ACCESS_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": JWT_REFRESH_LIFETIME,
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # géré explicitement au login
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

AUTH_REFRESH_COOKIE_NAME = env("AUTH_REFRESH_COOKIE_NAME", "at_refresh")
AUTH_REFRESH_COOKIE_PATH = "/api/v1/auth/"
AUTH_REFRESH_COOKIE_SECURE = env_bool("AUTH_REFRESH_COOKIE_SECURE", not DEBUG)
AUTH_REFRESH_COOKIE_SAMESITE = env("AUTH_REFRESH_COOKIE_SAMESITE", "Lax")

LOGIN_MAX_FAILED_ATTEMPTS = env_int("LOGIN_MAX_FAILED_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = env_int("LOGIN_LOCKOUT_MINUTES", 15)

# --------------------------------------------------------------------------
# HR-Skills Pay (Mobile Money pour la billetterie, carte optionnelle pour le vote)
# --------------------------------------------------------------------------
HRSKILLS_ENVIRONMENT = env("HRSKILLS_ENVIRONMENT", "test")
HRSKILLS_PUBLIC_KEY = env("HRSKILLS_PUBLIC_KEY", "")
HRSKILLS_SECRET_KEY = env("HRSKILLS_SECRET_KEY", "")
HRSKILLS_WEBHOOK_SECRET = env("HRSKILLS_WEBHOOK_SECRET", "")
HRSKILLS_BASE_URL = env("HRSKILLS_BASE_URL", "https://api.hrskills-pay.com")
# Contradiction relevée entre les SDK officiels sur le préfixe /sandbox (rapport §12) : configurable.
HRSKILLS_USE_SANDBOX_PREFIX = env_bool("HRSKILLS_USE_SANDBOX_PREFIX", True)
# Garde-fou volontaire : un simple HRSKILLS_ENVIRONMENT=live ne suffit pas à activer les paiements réels.
HRSKILLS_ALLOW_LIVE = env_bool("HRSKILLS_ALLOW_LIVE", False)
HRSKILLS_CARD_ENABLED = env_bool("HRSKILLS_CARD_ENABLED", False)
HRSKILLS_CARD_RETURN_URL = env("HRSKILLS_CARD_RETURN_URL", "")
# Une commande dont le paiement reste PENDING au-delà de ce délai est considérée expirée
# (filet de sécurité Celery Beat si le webhook n'arrive jamais).
HRSKILLS_PENDING_TIMEOUT_MINUTES = env_int("HRSKILLS_PENDING_TIMEOUT_MINUTES", 15)

# --------------------------------------------------------------------------
# Exposition des interfaces d'administration technique
# --------------------------------------------------------------------------
DJANGO_ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", DEBUG)
DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", "django-admin/")
API_DOCS_ENABLED = env_bool("API_DOCS_ENABLED", DEBUG)

# --------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL or "memory://")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULE = {
    "publish-scheduled-news": {
        "task": "apps.news.tasks.publish_scheduled_news",
        "schedule": 60.0,  # toutes les minutes
    },
    "expire-stale-pending-payments": {
        "task": "apps.payments.tasks.expire_stale_pending_payments",
        "schedule": 300.0,  # toutes les 5 minutes
    },
}

# --------------------------------------------------------------------------
# Logs (avec masquage des secrets)
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "apps.core.log_filters.SecretRedactingFilter"}},
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["redact"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
