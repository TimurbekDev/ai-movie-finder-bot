from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SearchHistory, User
from utils.i18n import DEFAULT_LANGUAGE, LANGUAGES, t

FREE_DAILY_LIMIT = 5
MAX_FILE_SIZE_MB = 20


def _detect_language(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LANGUAGE
    code = language_code.lower().split("-")[0]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    language_code: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            language=_detect_language(language_code),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_today_search_count(session: AsyncSession, user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    result = await session.execute(
        select(func.count(SearchHistory.id)).where(
            SearchHistory.user_id == user_id,
            SearchHistory.created_at >= since,
        )
    )
    return result.scalar_one()


async def can_search(session: AsyncSession, user: User) -> bool:
    if user.is_premium:
        return True
    count = await get_today_search_count(session, user.id)
    return count < FREE_DAILY_LIMIT


def is_file_too_large(file_size_bytes: int) -> bool:
    return file_size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024


def format_history(entries: list[SearchHistory], lang: str) -> str:
    if not entries:
        return t("history_empty", lang)
    lines = [t("history_header", lang)]
    for i, entry in enumerate(entries, start=1):
        lines.append(f"{i}. {entry.movie_name or t('unknown', lang)}")
    return "\n".join(lines)


async def get_overview_stats(session: AsyncSession) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
    premium_users = (
        await session.execute(select(func.count(User.id)).where(User.is_premium.is_(True)))
    ).scalar_one()
    new_users_today = (
        await session.execute(select(func.count(User.id)).where(User.created_at >= since))
    ).scalar_one()
    total_searches = (await session.execute(select(func.count(SearchHistory.id)))).scalar_one()
    searches_today = (
        await session.execute(select(func.count(SearchHistory.id)).where(SearchHistory.created_at >= since))
    ).scalar_one()
    return {
        "total_users": total_users,
        "premium_users": premium_users,
        "new_users_today": new_users_today,
        "total_searches": total_searches,
        "searches_today": searches_today,
    }


async def get_top_movies(session: AsyncSession, limit: int = 10) -> list[tuple[str, int]]:
    result = await session.execute(
        select(SearchHistory.movie_name, func.count(SearchHistory.id).label("cnt"))
        .where(SearchHistory.movie_name.is_not(None))
        .group_by(SearchHistory.movie_name)
        .order_by(func.count(SearchHistory.id).desc())
        .limit(limit)
    )
    return list(result.all())


async def get_active_users(session: AsyncSession, limit: int = 10) -> list[tuple[str | None, int, int]]:
    result = await session.execute(
        select(User.username, User.telegram_id, func.count(SearchHistory.id).label("cnt"))
        .join(SearchHistory, SearchHistory.user_id == User.id)
        .group_by(User.id)
        .order_by(func.count(SearchHistory.id).desc())
        .limit(limit)
    )
    return list(result.all())
