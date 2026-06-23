import asyncio
import logging

import requests

from config import TMDB_API_KEY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


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


def _search_movie_sync(title: str, year: str | None, language: str, region: str) -> dict | None:
    params = {"api_key": TMDB_API_KEY, "query": title, "language": language}
    if year:
        params["year"] = year

    resp = requests.get(f"{BASE_URL}/search/movie", params=params, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        return None

    movie_id = results[0]["id"]
    details_resp = requests.get(
        f"{BASE_URL}/movie/{movie_id}",
        params={
            "api_key": TMDB_API_KEY,
            "language": language,
            "append_to_response": "credits,videos,watch/providers",
        },
        timeout=10,
    )
    details_resp.raise_for_status()
    details = details_resp.json()

    cast = [c["name"] for c in details.get("credits", {}).get("cast", [])[:5]]

    trailer = None
    for v in details.get("videos", {}).get("results", []):
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            trailer = f"https://www.youtube.com/watch?v={v['key']}"
            break

    watch = _extract_watch_providers(details, region)

    return {
        "title": details.get("title"),
        "year": (details.get("release_date") or "")[:4],
        "genres": [g["name"] for g in details.get("genres", [])],
        "rating": details.get("vote_average"),
        "description": details.get("overview"),
        "actors": cast,
        "poster": f"{IMAGE_BASE}{details['poster_path']}" if details.get("poster_path") else None,
        "trailer": trailer,
        "watch_providers": watch["providers"],
        "watch_link": watch["link"],
    }


async def search_movie(
    title: str, year: str | None = None, language: str = "en-US", region: str = "US"
) -> dict | None:
    try:
        return await asyncio.to_thread(_search_movie_sync, title, year, language, region)
    except Exception:
        logger.exception("TMDB lookup failed for title=%s year=%s", title, year)
        return None
