import pytest
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import override_settings

from apps.publicapi.routing import websocket_urlpatterns
from apps.voting.services import adjust_votes


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


@pytest.mark.django_db(transaction=True)
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
def test_manual_vote_adjustment_reaches_connected_public_site(
    make_role, make_user, make_competition, make_category, make_candidate,
):
    competition = make_competition()
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    actor = make_user("votes-websocket@example.com", make_role("Votes", ["votes.adjust"]))

    async def connect_adjust_and_receive():
        communicator = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/api/v1/public/vote-events/")
        connected, _ = await communicator.connect()
        assert connected

        await sync_to_async(adjust_votes, thread_sensitive=True)(
            actor,
            candidate=candidate,
            delta=5,
            reason="Correction de saisie",
        )
        assert await communicator.receive_json_from(timeout=1) == {"event": "votes.updated"}
        await communicator.disconnect()

    async_to_sync(connect_adjust_and_receive)()
