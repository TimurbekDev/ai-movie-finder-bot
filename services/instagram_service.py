"""Instagram profile / posts / stories lookups.

anonyig's public API (api-wh.anonyig.com) was evaluated for this first. Its request
signature (`_s`) is produced by an obfuscated, browser-fingerprint-gated webpack
module that refuses to run outside a real browser, and the endpoint answers
CAPTCHA_REQUIRED (Cloudflare Turnstile) to everything else. Both are deliberate
anti-bot measures, so this talks to Instagram's own web API instead, reusing the
session cookie file yt-dlp already uses for reels.
"""

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from config import INSTAGRAM_COOKIES_FILE

logger = logging.getLogger(__name__)

# Public web app id -- the same constant instagram.com ships in its own bundle.
IG_APP_ID = "936619743392459"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

MAX_POSTS = 10
MAX_STORIES = 10
# Telegram refuses bot uploads past this, and only after the whole file is pushed.
MAX_MEDIA_BYTES = 50 * 1024 * 1024
_TIMEOUT = 20

_session = requests.Session()

# Paths under instagram.com/ that are features, not usernames.
RESERVED_PATHS = frozenset(
    {
        "p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct",
        "challenge", "s", "about", "developer", "legal", "privacy", "terms",
        "web", "graphql", "api", "oauth", "session",
    }
)

PROFILE_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/(?:stories/)?([A-Za-z0-9._]{1,30})/?",
    re.IGNORECASE,
)
# A bare handle counts only when it is the whole message, so the bot does not react
# to every @mention that happens to appear inside a sentence.
USERNAME_PATTERN = re.compile(r"^@([A-Za-z0-9._]{1,30})$")


class InstagramError(Exception):
    """Lookup failed for a reason worth showing the user."""


class ProfileNotFoundError(InstagramError):
    pass


class InstagramAuthError(InstagramError):
    """Cookies are missing or expired -- the API answered with a login wall."""


class RateLimitedError(InstagramError):
    """Instagram throttled this endpoint for our IP; it clears on its own."""


def extract_username(text: str) -> str | None:
    """Pull an Instagram handle out of a profile URL or a bare @handle."""
    handle = USERNAME_PATTERN.match((text or "").strip())
    if handle:
        return handle.group(1).lower()

    match = PROFILE_URL_PATTERN.search(text or "")
    if not match:
        return None
    username = match.group(1).lower()
    return None if username in RESERVED_PATHS else username


_cookies_cache: tuple[float, dict[str, str]] | None = None


def _load_cookies() -> dict[str, str]:
    """Parse the Netscape cookie jar, re-reading it when the file is refreshed."""
    global _cookies_cache
    path = INSTAGRAM_COOKIES_FILE
    if not path or not os.path.exists(path):
        return {}

    mtime = os.path.getmtime(path)
    if _cookies_cache and _cookies_cache[0] == mtime:
        return _cookies_cache[1]

    cookies: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) >= 7:
                    cookies[fields[5]] = fields[6]
    except OSError:
        logger.warning("Could not read Instagram cookie file %s", path, exc_info=True)
        return {}

    _cookies_cache = (mtime, cookies)
    return cookies


def _headers(cookies: dict[str, str]) -> dict[str, str]:
    headers = {
        "user-agent": USER_AGENT,
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "x-ig-app-id": IG_APP_ID,
        "x-requested-with": "XMLHttpRequest",
        "referer": "https://www.instagram.com/",
    }
    if "csrftoken" in cookies:
        headers["x-csrftoken"] = cookies["csrftoken"]
    return headers


def _api_get(url: str, params: dict | None = None) -> dict:
    cookies = _load_cookies()
    resp = _session.get(
        url, params=params, headers=_headers(cookies), cookies=cookies, timeout=_TIMEOUT
    )
    if resp.status_code in (401, 403):
        raise InstagramAuthError(f"{resp.status_code} from {url}")
    if resp.status_code == 404:
        raise ProfileNotFoundError(url)
    if resp.status_code == 429:
        raise RateLimitedError(url)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as e:
        # A login wall answers with HTML, not JSON.
        raise InstagramAuthError("non-JSON response (login wall?)") from e


def _topsearch_sync(username: str) -> dict:
    """Resolve a handle to its numeric id and the basics shown on the card.

    web_profile_info would return all of this in one call, but Instagram throttles
    that endpoint per IP far more aggressively than search, so identity resolution
    hangs off the endpoint that keeps answering.
    """
    data = _api_get(
        "https://www.instagram.com/api/v1/web/search/topsearch/", {"query": username}
    )
    for entry in data.get("users") or []:
        user = entry.get("user") or {}
        if (user.get("username") or "").lower() == username.lower():
            return {
                "id": str(user.get("pk") or user.get("pk_id") or ""),
                "username": user.get("username"),
                "full_name": user.get("full_name") or "",
                "is_private": bool(user.get("is_private")),
                "is_verified": bool(user.get("is_verified")),
                "profile_pic": user.get("profile_pic_url"),
                # Search carries no bio or counts; _enrich_profile fills them in.
                "biography": "",
                "external_url": "",
                "followers": None,
                "following": None,
                "posts_count": None,
            }
    raise ProfileNotFoundError(username)


def _web_profile_info_sync(username: str) -> dict:
    data = _api_get(
        "https://www.instagram.com/api/v1/users/web_profile_info/", {"username": username}
    )
    user = (data.get("data") or {}).get("user")
    if not user:
        raise ProfileNotFoundError(username)
    return user


def _fetch_profile_sync(username: str) -> dict:
    """Profile card, best-effort: identity always, bio and counts when available."""
    profile = _topsearch_sync(username)
    try:
        user = _web_profile_info_sync(profile["username"])
    except InstagramError as e:
        # Throttling here costs detail, not the feature -- the card still renders.
        logger.info("Profile detail unavailable for @%s (%s)", username, type(e).__name__)
        return profile

    profile.update(
        {
            "id": str(user.get("id") or profile["id"]),
            "full_name": user.get("full_name") or profile["full_name"],
            "biography": user.get("biography") or "",
            "external_url": user.get("external_url") or "",
            "followers": (user.get("edge_followed_by") or {}).get("count"),
            "following": (user.get("edge_follow") or {}).get("count"),
            "posts_count": (user.get("edge_owner_to_timeline_media") or {}).get("count"),
            "is_private": bool(user.get("is_private")),
            "is_verified": bool(user.get("is_verified")),
            "profile_pic": user.get("profile_pic_url_hd")
            or user.get("profile_pic_url")
            or profile["profile_pic"],
        }
    )
    return profile


def _best_url(candidates: list[dict]) -> str | None:
    """Highest-resolution entry of an image_versions2/video_versions list."""
    usable = [c for c in candidates or [] if c.get("url")]
    if not usable:
        return None
    return max(usable, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))["url"]


def _parse_media(node: dict) -> list[dict]:
    """Flatten one feed/story item into sendable media.

    media_type 8 is a carousel, so a single post can yield several files; the shape
    is shared by the timeline feed and the stories tray.
    """
    if node.get("media_type") == 8:
        items = []
        for child in node.get("carousel_media") or []:
            items.extend(_parse_media(child))
        return items

    caption = ((node.get("caption") or {}).get("text") or "").strip()
    common = {"caption": caption, "taken_at": node.get("taken_at")}

    if node.get("media_type") == 2 or node.get("video_versions"):
        url = _best_url(node.get("video_versions") or [])
        if url:
            return [{**common, "type": "video", "url": url}]

    url = _best_url((node.get("image_versions2") or {}).get("candidates") or [])
    if url:
        return [{**common, "type": "photo", "url": url}]
    return []


def _parse_graphql_node(node: dict) -> list[dict]:
    """Flatten one timeline node.

    web_profile_info returns the older GraphQL shape, which names every field
    differently from the mobile feed that stories come from -- hence the second
    parser rather than one that tries to speak both.
    """
    if node.get("__typename") == "GraphSidecar":
        items = []
        for edge in ((node.get("edge_sidecar_to_children") or {}).get("edges") or []):
            items.extend(_parse_graphql_node(edge.get("node") or {}))
        return items

    caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    caption = ""
    if caption_edges:
        caption = ((caption_edges[0].get("node") or {}).get("text") or "").strip()
    common = {"caption": caption, "taken_at": node.get("taken_at_timestamp")}

    if node.get("is_video") and node.get("video_url"):
        return [{**common, "type": "video", "url": node["video_url"]}]
    if node.get("display_url"):
        return [{**common, "type": "photo", "url": node["display_url"]}]
    return []


def _fetch_posts_sync(username: str, limit: int) -> list[dict]:
    user = _web_profile_info_sync(username)
    edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges") or []
    media: list[dict] = []
    for edge in edges:
        media.extend(_parse_graphql_node(edge.get("node") or {}))
        if len(media) >= limit:
            break
    return media[:limit]


def _fetch_stories_sync(user_id: str, limit: int) -> list[dict]:
    data = _api_get(
        "https://www.instagram.com/api/v1/feed/reels_media/", {"reel_ids": user_id}
    )
    reels = data.get("reels") or data.get("reels_media") or {}
    if isinstance(reels, list):  # reels_media form: a list of trays
        reel = reels[0] if reels else None
    else:
        reel = reels.get(str(user_id))
    if not reel:
        return []

    media: list[dict] = []
    for item in reel.get("items") or []:
        media.extend(_parse_media(item))
        if len(media) >= limit:
            break
    return media[:limit]


def _download_sync(url: str) -> bytes | None:
    """Pull one CDN file, skipping anything Telegram would refuse to upload."""
    try:
        with _session.get(url, headers={"user-agent": USER_AGENT}, timeout=60, stream=True) as r:
            r.raise_for_status()
            declared = int(r.headers.get("content-length") or 0)
            if declared > MAX_MEDIA_BYTES:
                logger.info("Skipping %d-byte Instagram file (over Telegram limit)", declared)
                return None
            chunks, total = [], 0
            for chunk in r.iter_content(1 << 16):
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:  # chunked responses declare no length
                    logger.info("Skipping oversized Instagram file (no content-length)")
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception:
        logger.warning("Instagram media download failed for %s", url, exc_info=True)
        return None


def _download_all_sync(urls: list[str]) -> list[bytes | None]:
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=min(4, len(urls))) as pool:
        return list(pool.map(_download_sync, urls))


async def fetch_profile(username: str) -> dict:
    return await asyncio.to_thread(_fetch_profile_sync, username)


async def fetch_posts(username: str, limit: int = MAX_POSTS) -> list[dict]:
    return await asyncio.to_thread(_fetch_posts_sync, username, limit)


async def fetch_stories(user_id: str, limit: int = MAX_STORIES) -> list[dict]:
    return await asyncio.to_thread(_fetch_stories_sync, user_id, limit)


async def download_media(urls: list[str]) -> list[bytes | None]:
    """Fetch several CDN files at once; a None entry means that one is unsendable."""
    return await asyncio.to_thread(_download_all_sync, urls)
