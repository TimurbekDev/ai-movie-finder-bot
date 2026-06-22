import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message


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
        user_id = event.from_user.id
        now = time.monotonic()
        if now - self._last_call[user_id] < self.rate_limit:
            return None
        self._last_call[user_id] = now
        return await handler(event, data)
