"""WebSocket /ws/notifications?token=<access token>: pushes "notification.new" so the bell
badge updates at once. The browser falls back to polling every 60 seconds."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .services import group_name


@database_sync_to_async
def user_from_token(token: str) -> Any:
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    auth = JWTAuthentication()
    try:
        validated = auth.get_validated_token(token.encode())
        user = auth.get_user(validated)
    except (InvalidToken, TokenError, Exception):  # noqa: BLE001
        return None
    return user if user.is_active else None


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    group: str | None = None

    async def connect(self) -> None:
        query = parse_qs(self.scope.get("query_string", b"").decode())
        user = await user_from_token((query.get("token") or [""])[0])
        if user is None:
            await self.close(code=4401)
            return
        self.group = group_name(user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello"})

    async def disconnect(self, code: int) -> None:
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def notification_new(self, event: dict[str, Any]) -> None:
        await self.send_json(event)
