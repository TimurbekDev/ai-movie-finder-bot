import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.handlers import VIDEO_LINK_PATTERN


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
        is_heavy = event.photo or event.video or (event.text and VIDEO_LINK_PATTERN.search(event.text))
        if not is_heavy:
            return await handler(event, data)

        user_id = event.from_user.id
        now = time.monotonic()
        if now - self._last_call[user_id] < self.rate_limit:
            return None
        self._last_call[user_id] = now
        return await handler(event, data)
