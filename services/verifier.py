"""Resolve AI candidates against TMDB and produce a calibrated confidence.

Takes the ranked candidate list from the vision model and finds the best-matching
real TMDB entity, scoring each on title similarity, release year, media type, cast
overlap and popularity. Confidence is DERIVED from these signals plus cross-frame
agreement -- not the model's self-reported number.

Two-pass to bound cost: a cheap prelim score (no extra API calls) ranks all hits,
then full details (which include credits) are fetched only for the top few.
"""

import logging

from rapidfuzz import fuzz

from services import tmdb_service

logger = logging.getLogger(__name__)

_DETAIL_FETCH_LIMIT = 3  # how many top hits get a (costly) details call


def _norm_conf(value) -> float:
    """AI confidence -> 0..1. Accepts int/float, '85', '85%', or None."""
    if value is None:
        return 0.5
    try:
        return max(0.0, min(1.0, float(str(value).replace("%", "").strip()) / 100.0))
    except (ValueError, TypeError):
        return 0.5


def _year_score(ai_year, tmdb_year) -> float:
    if not ai_year or not tmdb_year:
        return 0.5
    try:
        d = abs(int(ai_year) - int(tmdb_year))
    except (ValueError, TypeError):
        return 0.5
    return 1.0 if d == 0 else 0.7 if d == 1 else 0.3 if d <= 3 else 0.0


def _media_score(ai_media, tmdb_media) -> float:
    if not ai_media:
        return 1.0  # AI didn't commit -> don't penalize
    return 1.0 if ai_media == tmdb_media else 0.4


def _title_sim(cand: dict, tmdb_title: str) -> float:
    candidates = [cand.get("title", "")] + list(cand.get("alternative_titles") or [])
    best = max((fuzz.token_set_ratio(c or "", tmdb_title or "") for c in candidates), default=0)
    return best / 100.0


def _cast_overlap(ai_actors, tmdb_cast) -> float:
    if not ai_actors or not tmdb_cast:
        return 0.0
    tc = [c.lower() for c in tmdb_cast]
    hits = sum(1 for a in ai_actors if any(fuzz.partial_ratio(a.lower(), c) > 85 for c in tc))
    return min(1.0, hits / len(ai_actors))


def _prelim_score(cand: dict, hit: dict) -> float:
    """Cheap score without cast (max 0.80); cast adds the remaining 0.20 later."""
    return (
        0.45 * _title_sim(cand, hit.get("title", ""))
        + 0.15 * _year_score(cand.get("year"), hit.get("year"))
        + 0.10 * _media_score(cand.get("media_type"), hit.get("media_type"))
        + 0.10 * min(1.0, (hit.get("popularity") or 0.0) / 50.0)
    )


async def resolve(
    candidates: list[dict],
    language: str = "en-US",
    region: str = "US",
) -> dict | None:
    """Best TMDB entity for the candidate list, enriched with calibrated confidence."""
    scored: list[tuple[float, dict, dict]] = []
    for cand in candidates[:4]:
        hits = await tmdb_service.search_multi(cand.get("title"), cand.get("year"), language)
        for hit in hits[:5]:
            scored.append((_prelim_score(cand, hit), cand, hit))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)

    best = None
    for prelim, cand, hit in scored[:_DETAIL_FETCH_LIMIT]:
        details = await tmdb_service.get_details(hit["id"], hit["media_type"], language, region)
        if not details:
            continue
        match = min(1.0, prelim + 0.20 * _cast_overlap(cand.get("actors") or [], details.get("actors") or []))
        final = 0.65 * match + 0.35 * _norm_conf(cand.get("confidence"))
        if best is None or final > best[0]:
            best = (final, details, cand)

    if not best:
        return None

    final, details, cand = best
    details["confidence"] = round(final * 100)
    details["reasoning"] = cand.get("reasoning") or cand.get("scene") or ""
    details["alternatives"] = [c.get("title") for c in candidates[1:3] if c.get("title")]
    return details
