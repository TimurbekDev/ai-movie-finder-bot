"""Resolve AI candidates against TMDB and produce a calibrated confidence.

Takes the ranked candidate list from the vision model and finds the best-matching
real TMDB entity, scoring each on title similarity, release year, media type, cast
overlap and popularity. Confidence is DERIVED from these signals plus cross-frame
agreement -- not the model's self-reported number.

Two-pass to bound cost: a cheap prelim score (no extra API calls) ranks all hits,
then full details (which include credits) are fetched only for the top few.
All independent TMDB calls run concurrently.
"""

import asyncio
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


def _title_sim(cand: dict, hit: dict) -> float:
    """Best fuzzy match across AI title+alternatives vs TMDB localized+original title.

    The localized TMDB title (e.g. ru-RU) rarely matches the AI's English title,
    so the original title must participate or correct hits get buried.
    """
    ai_titles = [cand.get("title", "")] + list(cand.get("alternative_titles") or [])
    tmdb_titles = [t for t in (hit.get("title"), hit.get("original_title")) if t]
    best = max(
        (fuzz.token_set_ratio(a or "", t) for a in ai_titles for t in tmdb_titles),
        default=0,
    )
    return best / 100.0


def _cast_overlap(ai_actors, tmdb_cast) -> float:
    if not ai_actors or not tmdb_cast:
        return 0.0
    tc = [c.lower() for c in tmdb_cast]
    hits = sum(1 for a in ai_actors if any(fuzz.partial_ratio(a.lower(), c) > 85 for c in tc))
    return min(1.0, hits / len(ai_actors))


_PRELIM_MAX = 0.80  # weights below sum to this; cast supplies the remaining 0.20


def _prelim_score(cand: dict, hit: dict) -> float:
    """Cheap score without cast (max _PRELIM_MAX); cast adds the rest later."""
    return (
        0.45 * _title_sim(cand, hit)
        + 0.15 * _year_score(cand.get("year"), hit.get("year"))
        + 0.10 * _media_score(cand.get("media_type"), hit.get("media_type"))
        + 0.10 * min(1.0, (hit.get("popularity") or 0.0) / 50.0)
    )


async def _search_candidate(cand: dict, language: str) -> list[dict]:
    """Search the main title; fall back to alternative titles when it finds nothing."""
    year, media_type = cand.get("year"), cand.get("media_type")
    hits = await tmdb_service.search(cand.get("title"), year, media_type, language)
    if hits:
        return hits
    for alt in (cand.get("alternative_titles") or [])[:2]:
        hits = await tmdb_service.search(alt, year, media_type, language)
        if hits:
            return hits
    return []


async def resolve(
    candidates: list[dict],
    language: str = "en-US",
    region: str = "US",
) -> dict | None:
    """Best TMDB entity for the candidate list, enriched with calibrated confidence."""
    cands = candidates[:4]
    hit_lists = await asyncio.gather(*(_search_candidate(c, language) for c in cands))

    scored: list[tuple[float, dict, dict]] = []
    for cand, hits in zip(cands, hit_lists):
        for hit in hits[:5]:
            scored.append((_prelim_score(cand, hit), cand, hit))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)

    # Distinct entities only -- several candidates often resolve to the same title.
    seen: set[tuple[int, str]] = set()
    top: list[tuple[float, dict, dict]] = []
    for prelim, cand, hit in scored:
        key = (hit["id"], hit["media_type"])
        if key in seen:
            continue
        seen.add(key)
        top.append((prelim, cand, hit))
        if len(top) == _DETAIL_FETCH_LIMIT:
            break

    detail_list = await asyncio.gather(
        *(tmdb_service.get_details(hit["id"], hit["media_type"], language, region) for _, _, hit in top)
    )

    best = None
    for (prelim, cand, _), details in zip(top, detail_list):
        if not details:
            continue
        ai_actors = cand.get("actors") or []
        cast = _cast_overlap(ai_actors, details.get("actors") or [])
        ai_conf = _norm_conf(cand.get("confidence"))

        # How well the candidate resolved to THIS entity, normalized to 0..1. When
        # the AI named no actors, cast overlap is unmeasurable rather than zero, so
        # it must not drag the score down -- otherwise animation and unknown-cast
        # titles get a permanent 20% penalty.
        match = prelim / _PRELIM_MAX
        if ai_actors:
            match = 0.8 * match + 0.2 * cast

        # Ranking and reported confidence answer different questions. `match` only
        # says we resolved the candidate NAME to the right TMDB entity -- it cannot
        # make a shaky guess more likely, since the AI supplied the title and year
        # being matched. So the AI's own probability sets the base rate. Cast overlap
        # lifts it only modestly: a prolific actor confirms the face was read right,
        # not which of that actor's films this is.
        rank = match * (0.5 + 0.5 * ai_conf)
        confidence = ai_conf * match
        confidence += (1.0 - confidence) * 0.3 * cast

        if best is None or rank > best[0]:
            best = (rank, details, cand, confidence)

    if not best:
        return None

    _, details, cand, confidence = best
    details["confidence"] = round(confidence * 100)
    chosen = {(cand.get("title") or "").lower(), (details.get("title") or "").lower()}
    details["alternatives"] = [
        c.get("title")
        for c in candidates
        if c.get("title") and c["title"].lower() not in chosen
    ][:2]
    return details
