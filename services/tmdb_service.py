import asyncio
import logging

import requests

from config import TMDB_API_KEY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _search_movie_sync(title: str, year: str | None, language: str) -> dict | None:
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
        params={"api_key": TMDB_API_KEY, "language": language, "append_to_response": "credits,videos"},
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

    return {
        "title": details.get("title"),
        "year": (details.get("release_date") or "")[:4],
        "genres": [g["name"] for g in details.get("genres", [])],
        "rating": details.get("vote_average"),
        "description": details.get("overview"),
        "actors": cast,
        "poster": f"{IMAGE_BASE}{details['poster_path']}" if details.get("poster_path") else None,
        "trailer": trailer,
    }


async def search_movie(title: str, year: str | None = None, language: str = "en-US") -> dict | None:
    try:
        return await asyncio.to_thread(_search_movie_sync, title, year, language)
    except Exception:
        logger.exception("TMDB lookup failed for title=%s year=%s", title, year)
        return None
