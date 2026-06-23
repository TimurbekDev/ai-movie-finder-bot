"""Perceptual-hash dedup cache.

Avoids repeat AI/TMDB calls for the same (or near-identical) screenshot.
Lookup uses Postgres bit_count over XOR for exact hamming distance (requires
PostgreSQL 14+). Every operation is non-fatal: on any error it logs and behaves
as a cache miss so the normal pipeline always proceeds.
"""

import json
import logging

from sqlalchemy import text

from database.models import IdentificationCache

logger = logging.getLogger(__name__)

HAMMING_THRESHOLD = 6  # <=6 differing bits ~ visually the same frame; tune 4..10


async def lookup(session, phash: int) -> dict | None:
    """Return the cached result dict for the nearest image within threshold, else None."""
    try:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, result_json
                    FROM identification_cache
                    WHERE bit_count(phash # :q) <= :thr
                    ORDER BY bit_count(phash # :q) ASC
                    LIMIT 1
                    """
                ),
                {"q": phash, "thr": HAMMING_THRESHOLD},
            )
        ).first()
        if not row:
            return None
        await session.execute(
            text("UPDATE identification_cache SET hits = hits + 1 WHERE id = :id"),
            {"id": row.id},
        )
        await session.commit()
        return json.loads(row.result_json)
    except Exception:
        logger.exception("Cache lookup failed; treating as miss")
        await session.rollback()
        return None


async def store(session, phash: int, result: dict) -> None:
    """Persist a fresh identification result keyed by perceptual hash."""
    try:
        session.add(
            IdentificationCache(
                phash=phash,
                tmdb_id=result.get("tmdb_id"),
                media_type=result.get("media_type"),
                result_json=json.dumps(result, ensure_ascii=False),
            )
        )
        await session.commit()
    except Exception:
        logger.exception("Cache store failed")
        await session.rollback()
