import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.publicapi.routing import websocket_urlpatterns


@pytest.mark.django_db
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
def test_public_vote_events_websocket_broadcasts_updates():
    async def connect_and_receive_update():
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/api/v1/public/vote-events/")
        connected, _ = await communicator.connect()
        assert connected

        await get_channel_layer().group_send(
            "public_vote_updates",
            {"type": "vote.updated"},
        )
        assert await communicator.receive_json_from(timeout=1) == {"event": "votes.updated"}
        await communicator.disconnect()

    async_to_sync(connect_and_receive_update)()
