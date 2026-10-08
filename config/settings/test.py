import tempfile

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
AUTH_REFRESH_COOKIE_SECURE = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SECURE_SSL_REDIRECT = False
MEDIA_ROOT = tempfile.mkdtemp(prefix="at-test-media-")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Débit très élevé pour ne pas perturber les tests (les tests de limitation le réduisent explicitement)
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100000/min", "user": "100000/min", "login": "100000/min", "refresh": "100000/min",
        "webhook": "100000/min", "vote_order": "100000/min",
    },
}
