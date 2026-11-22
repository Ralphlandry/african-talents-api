from channels.generic.websocket import AsyncJsonWebsocketConsumer


class PublicVoteEventsConsumer(AsyncJsonWebsocketConsumer):
    group_name = "public_vote_updates"

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def vote_updated(self, event):
        await self.send_json({"event": "votes.updated"})
