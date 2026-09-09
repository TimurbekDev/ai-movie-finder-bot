import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.handlers import INSTAGRAM_PROFILE_TRIGGER, VIDEO_LINK_PATTERN


class ThrottlingMiddleware(BaseMiddleware):
    """Drops messages from a user arriving faster than rate_limit seconds apart."""

    def __init__(self, rate_limit: float = 2.0) -> None:
        self.rate_limit = rate_limit
        self._last_call: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        text = event.text or ""
        is_heavy = bool(
            event.photo
            or event.video
            or VIDEO_LINK_PATTERN.search(text)
            or INSTAGRAM_PROFILE_TRIGGER.search(text)
        )
        if not is_heavy:
            return await handler(event, data)

        user_id = event.from_user.id
        now = time.monotonic()
        if now - self._last_call[user_id] < self.rate_limit:
            return None
        self._last_call[user_id] = now

        if len(self._last_call) > 10_000:  # bound memory on long uptimes
            cutoff = now - self.rate_limit
            self._last_call = defaultdict(
                float, {uid: ts for uid, ts in self._last_call.items() if ts > cutoff}
            )
        return await handler(event, data)
