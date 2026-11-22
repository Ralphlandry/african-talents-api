import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django_application = get_asgi_application()

from apps.publicapi.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_application,
        "websocket": OriginValidator(
            URLRouter(websocket_urlpatterns),
            settings.CORS_ALLOWED_ORIGINS,
        ),
    }
)
