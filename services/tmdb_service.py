import asyncio
import logging

import requests

from config import TMDB_API_KEY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

_session = requests.Session()  # keep-alive across calls


def _extract_watch_providers(details: dict, region: str) -> dict:
    """Pulls streaming/rent/buy provider names + JustWatch link for the given region."""
    region_data = details.get("watch/providers", {}).get("results", {}).get(region)
    if not region_data:
        return {"providers": [], "link": None}

    names = []
    for kind in ("flatrate", "free", "ads", "rent", "buy"):
        for p in region_data.get(kind, []):
            name = p.get("provider_name")
            if name and name not in names:
                names.append(name)

    return {"providers": names[:6], "link": region_data.get("link")}


def _search_sync(title: str, year: str | None, media_type: str | None, language: str) -> list[dict]:
    """Type-aware search; retry without the year filter on empty.

    /search/multi silently ignores year params, so when the AI committed to a
    media type we use /search/movie or /search/tv where the year filter works.
    """
    if not title:
        return []

    if media_type == "movie":
        endpoint, year_param = "/search/movie", "primary_release_year"
    elif media_type == "tv":
        endpoint, year_param = "/search/tv", "first_air_date_year"
    else:
        endpoint, year_param = "/search/multi", None

    def _query(extra: dict) -> list[dict]:
        resp = _session.get(
            f"{BASE_URL}{endpoint}",
            params={
                "api_key": TMDB_API_KEY,
                "language": language,
                "query": title,
                "include_adult": "false",
                **extra,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    use_year = bool(year and year_param)
    raw = _query({year_param: year}) if use_year else _query({})
    if not raw and use_year:
        raw = _query({})  # bad/missing AI year shouldn't kill the lookup

    out = []
    for r in raw:
        rtype = r.get("media_type") or media_type
        if rtype not in ("movie", "tv"):
            continue  # skip person results
        out.append(
            {
                "id": r["id"],
                "media_type": rtype,
                "title": r.get("title") or r.get("name"),
                "original_title": r.get("original_title") or r.get("original_name"),
                "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
                "popularity": r.get("popularity") or 0.0,
            }
        )
    return out


def _details_sync(tmdb_id: int, media_type: str, language: str, region: str) -> dict | None:
    resp = _session.get(
        f"{BASE_URL}/{media_type}/{tmdb_id}",
        params={
            "api_key": TMDB_API_KEY,
            "language": language,
            "append_to_response": "credits,videos,watch/providers",
        },
        timeout=10,
    )
    resp.raise_for_status()
    details = resp.json()

    cast = [c["name"] for c in details.get("credits", {}).get("cast", [])[:5]]

    trailer = None
    for v in details.get("videos", {}).get("results", []):
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            trailer = f"https://www.youtube.com/watch?v={v['key']}"
            break

    watch = _extract_watch_providers(details, region)
    date = details.get("release_date") or details.get("first_air_date") or ""

    return {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": details.get("title") or details.get("name"),
        "year": date[:4],
        "genres": [g["name"] for g in details.get("genres", [])],
        "rating": details.get("vote_average"),
        "description": details.get("overview"),
        "actors": cast,
        "poster": f"{IMAGE_BASE}{details['poster_path']}" if details.get("poster_path") else None,
        "trailer": trailer,
        "watch_providers": watch["providers"],
        "watch_link": watch["link"],
    }


async def search(
    title: str,
    year: str | None = None,
    media_type: str | None = None,
    language: str = "en-US",
) -> list[dict]:
    try:
        return await asyncio.to_thread(_search_sync, title, year, media_type, language)
    except Exception:
        logger.exception("TMDB search failed for title=%s year=%s type=%s", title, year, media_type)
        return []


async def get_details(
    tmdb_id: int, media_type: str, language: str = "en-US", region: str = "US"
) -> dict | None:
    try:
        return await asyncio.to_thread(_details_sync, tmdb_id, media_type, language, region)
    except Exception:
        logger.exception("TMDB details failed for id=%s type=%s", tmdb_id, media_type)
        return None
