"""Change tracking for looked-up Instagram profiles.

Keeps one row per handle (InstagramSnapshot) and, on every fresh lookup,
diffs the new profile against it -- avatar swapped, bio edited, a highlight
added or removed -- before overwriting it. Like cache_service, every
operation is non-fatal: on any error it logs and returns "nothing changed"
so a profile lookup never fails because the diff couldn't be computed.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import InstagramSnapshot
from services.image_service import hamming, phash

logger = logging.getLogger(__name__)

# Same tolerance cache_service uses for "visually the same picture" -- small
# CDN re-encodes shouldn't read as an avatar change.
AVATAR_HAMMING_THRESHOLD = 6

# Change codes diff_and_store() may return, most to least visible.
AVATAR_CHANGED = "avatar"
NAME_CHANGED = "name"
BIO_CHANGED = "bio"
HIGHLIGHTS_ADDED = "highlights_up"
HIGHLIGHTS_REMOVED = "highlights_down"


async def diff_and_store(session: AsyncSession, profile: dict, avatar_bytes: bytes | None) -> list[str]:
    """Compare `profile` against the last snapshot for its username, persist
    the new snapshot, and return the list of change codes found. Empty on the
    very first lookup of a handle -- there is nothing yet to compare against.
    """
    username = profile["username"]
    avatar_hash = None
    if avatar_bytes:
        try:
            avatar_hash = phash(avatar_bytes)
        except Exception:
            logger.warning("Avatar phash failed for @%s", username, exc_info=True)

    try:
        existing = (
            await session.execute(
                select(InstagramSnapshot).where(InstagramSnapshot.username == username)
            )
        ).scalar_one_or_none()

        changes: list[str] = []
        if existing:
            if (
                avatar_hash is not None
                and existing.avatar_phash is not None
                and hamming(avatar_hash, existing.avatar_phash) > AVATAR_HAMMING_THRESHOLD
            ):
                changes.append(AVATAR_CHANGED)
            if (profile.get("full_name") or "") != (existing.full_name or ""):
                changes.append(NAME_CHANGED)
            if (profile.get("biography") or "") != (existing.biography or ""):
                changes.append(BIO_CHANGED)

            new_count, old_count = profile.get("highlight_count"), existing.highlight_count
            if new_count is not None and old_count is not None:
                if new_count > old_count:
                    changes.append(HIGHLIGHTS_ADDED)
                elif new_count < old_count:
                    changes.append(HIGHLIGHTS_REMOVED)

            existing.full_name = profile.get("full_name") or None
            existing.biography = profile.get("biography") or None
            existing.is_private = bool(profile.get("is_private"))
            if avatar_hash is not None:
                existing.avatar_phash = avatar_hash
            if profile.get("highlight_count") is not None:
                existing.highlight_count = profile["highlight_count"]
        else:
            session.add(
                InstagramSnapshot(
                    username=username,
                    full_name=profile.get("full_name") or None,
                    biography=profile.get("biography") or None,
                    avatar_phash=avatar_hash,
                    highlight_count=profile.get("highlight_count"),
                    is_private=bool(profile.get("is_private")),
                )
            )

        await session.commit()
        return changes
    except Exception:
        logger.exception("Instagram snapshot diff/store failed for @%s", username)
        await session.rollback()
        return []
