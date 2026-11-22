from django.urls import path

from .consumers import PublicVoteEventsConsumer

websocket_urlpatterns = [
    path("api/v1/public/vote-events/", PublicVoteEventsConsumer.as_asgi()),
]
