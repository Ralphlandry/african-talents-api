from .base import *  # noqa: F401,F403
from .base import CORS_ALLOWED_ORIGINS, env_bool

DEBUG = env_bool("DEBUG", True)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:5174"]
