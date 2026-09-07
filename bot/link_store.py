"""Short-lived token -> URL map for link action buttons.

Telegram caps callback_data at 64 bytes, which a full YouTube/Instagram URL can
overrun, so the link is parked here and only an opaque token travels in the button.
"""

import secrets
import time

TTL_SEC = 60 * 60
MAX_ENTRIES = 5000

_links: dict[str, tuple[str, float]] = {}


def _purge(now: float) -> None:
    expired = [token for token, (_, ts) in _links.items() if now - ts > TTL_SEC]
    for token in expired:
        _links.pop(token, None)
    # Hard cap in case a burst of links arrives inside a single TTL window.
    while len(_links) > MAX_ENTRIES:
        oldest = min(_links, key=lambda k: _links[k][1])
        _links.pop(oldest, None)


def put(url: str) -> str:
    now = time.time()
    _purge(now)
    token = secrets.token_urlsafe(8)
    _links[token] = (url, now)
    return token


def get(token: str) -> str | None:
    entry = _links.get(token)
    if entry is None:
        return None
    url, ts = entry
    if time.time() - ts > TTL_SEC:
        _links.pop(token, None)
        return None
    return url
