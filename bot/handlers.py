import logging
import os
import re
import tempfile

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import select

from bot.keyboards import admin_panel_keyboard, language_keyboard, main_menu_keyboard, movie_result_keyboard
from config import ADMIN_IDS
from database.database import get_session
from database.models import SearchHistory
from services import cache_service, image_service, openai_service, verifier, video_service
from services.video_service import VideoTooLongError
from utils.helpers import (
    FREE_DAILY_LIMIT,
    can_search,
    format_history,
    get_active_users,
    get_or_create_user,
    get_overview_stats,
    get_top_movies,
    is_file_too_large,
)
from utils.i18n import LANGUAGES, all_variants, t, tmdb_language, tmdb_region

logger = logging.getLogger(__name__)
router = Router()

HISTORY_BUTTON_TEXTS = all_variants("menu_history")
LANGUAGE_BUTTON_TEXTS = all_variants("menu_language")

YOUTUBE_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/shorts/[\w-]+|youtu\.be/[\w-]+|youtube\.com/watch\?v=[\w-]+)",
    re.IGNORECASE,
)

INSTAGRAM_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/[\w-]+",
    re.IGNORECASE,
)

VIDEO_LINK_PATTERN = re.compile(
    f"(?:{YOUTUBE_URL_PATTERN.pattern})|(?:{INSTAGRAM_URL_PATTERN.pattern})",
    re.IGNORECASE,
)

ADMIN_MAX_LINK_DURATION_SEC = 24 * 3600


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
    await message.answer(t("start", user.language), reply_markup=main_menu_keyboard(user.language))


@router.message(Command("language"))
@router.message(F.text.in_(LANGUAGE_BUTTON_TEXTS))
async def cmd_language(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
    await message.answer(t("choose_language", user.language), reply_markup=language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(callback: CallbackQuery) -> None:
    lang = callback.data.split(":", 1)[1]
    if lang not in LANGUAGES:
        await callback.answer()
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.username, callback.from_user.language_code
        )
        user.language = lang
        await session.commit()

    await callback.message.edit_text(t("language_set", lang))
    await callback.message.answer(t("start", lang), reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@router.message(Command("history"))
@router.message(F.text.in_(HISTORY_BUTTON_TEXTS))
async def cmd_history(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        result = await session.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(10)
        )
        entries = result.scalars().all()
    await message.answer(format_history(entries, user.language))


def _format_overview(stats: dict) -> str:
    return (
        "📊 <b>Bot overview</b>\n\n"
        f"👤 Total users: {stats['total_users']}\n"
        f"🆕 New users today: {stats['new_users_today']}\n"
        f"⭐ Premium users: {stats['premium_users']}\n\n"
        f"🔍 Total searches: {stats['total_searches']}\n"
        f"📅 Searches today: {stats['searches_today']}"
    )


def _format_top_movies(rows: list[tuple[str, int]]) -> str:
    if not rows:
        return "🎬 <b>Top movies</b>\n\nNo searches yet."
    lines = ["🎬 <b>Top movies</b>\n"]
    for i, (name, count) in enumerate(rows, start=1):
        lines.append(f"{i}. {name} — {count}")
    return "\n".join(lines)


def _format_active_users(rows: list[tuple[str | None, int, int]]) -> str:
    if not rows:
        return "👥 <b>Active users</b>\n\nNo searches yet."
    lines = ["👥 <b>Active users</b>\n"]
    for i, (username, telegram_id, count) in enumerate(rows, start=1):
        label = f"@{username}" if username else str(telegram_id)
        lines.append(f"{i}. {label} — {count} searches")
    return "\n".join(lines)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    async with get_session() as session:
        stats = await get_overview_stats(session)
    await message.answer(_format_overview(stats), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_panel(callback: CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return

    action = callback.data.split(":", 1)[1]
    async with get_session() as session:
        if action == "movies":
            text = _format_top_movies(await get_top_movies(session))
        elif action == "active":
            text = _format_active_users(await get_active_users(session))
        else:
            text = _format_overview(await get_overview_stats(session))

    try:
        await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


def _top_candidate(analysis: dict) -> dict | None:
    candidates = analysis.get("candidates") or []
    return candidates[0] if candidates else None


def _format_movie_reply(analysis: dict, tmdb_result: dict | None, lang: str) -> str:
    top = _top_candidate(analysis)
    if not top:
        return t("not_identified", lang)

    if not tmdb_result:
        return (
            f"🎬 {top.get('title')} ({top.get('year') or '?'})\n\n"
            f"{t('confidence_label', lang)}: {top.get('confidence', '?')}%\n\n"
            f"{t('no_tmdb_details', lang)}"
        )

    genres = ", ".join(tmdb_result.get("genres", [])) or t("unknown", lang)
    actors = ", ".join(tmdb_result.get("actors", [])) or t("unknown", lang)
    reply = (
        f"🎬 {tmdb_result['title']} ({tmdb_result.get('year', '?')})\n\n"
        f"{t('genre_label', lang)}: {genres}\n"
        f"{t('rating_label', lang)}: {tmdb_result.get('rating', '?')}/10\n"
        f"{t('confidence_label', lang)}: {tmdb_result.get('confidence', '?')}%\n\n"
        f"{tmdb_result.get('description', '')}\n\n"
        f"{t('cast_label', lang)}: {actors}"
    )

    providers = tmdb_result.get("watch_providers") or []
    if providers:
        reply += f"\n{t('watch_label', lang)}: {', '.join(providers)}"

    alternatives = [a for a in (tmdb_result.get("alternatives") or []) if a]
    if alternatives:
        reply += f"\n\n{t('also_maybe', lang)}: {', '.join(alternatives)}"

    return reply


async def _save_history(
    session, user_id: int, file_type: str, analysis: dict, tmdb_result: dict | None
) -> None:
    top = _top_candidate(analysis) or {}
    name = (tmdb_result or {}).get("title") or top.get("title")
    conf = (tmdb_result or {}).get("confidence")
    session.add(
        SearchHistory(
            user_id=user_id,
            file_type=file_type,
            movie_name=name,
            confidence=str(conf) if conf is not None else None,
        )
    )
    await session.commit()


async def _deliver_result(message: Message, analysis: dict, lang: str, file_type: str) -> None:
    candidates = analysis.get("candidates") or []
    tmdb_result = None
    if candidates:
        tmdb_result = await verifier.resolve(
            candidates, language=tmdb_language(lang), region=tmdb_region(lang)
        )

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        await _save_history(session, user.id, file_type, analysis, tmdb_result)

    reply_text = _format_movie_reply(analysis, tmdb_result, lang)
    keyboard = movie_result_keyboard(
        tmdb_result.get("trailer") if tmdb_result else None,
        tmdb_result.get("watch_link") if tmdb_result else None,
        lang,
    )

    if tmdb_result and tmdb_result.get("poster"):
        await message.answer_photo(tmdb_result["poster"], caption=reply_text, reply_markup=keyboard)
    else:
        await message.answer(reply_text, reply_markup=keyboard)


@router.message(F.photo)
async def handle_photo(message: Message) -> None:
    photo = message.photo[-1]

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        lang = user.language
        is_admin = _is_admin(message.from_user.id)

        if not is_admin and is_file_too_large(photo.file_size or 0):
            await message.answer(t("file_too_large_image", lang))
            return

        if not is_admin and not await can_search(session, user):
            await message.answer(t("limit_reached", lang, limit=FREE_DAILY_LIMIT))
            return

    status_msg = await message.answer(t("analyzing_image", lang))
    try:
        file = await message.bot.get_file(photo.file_id)
        buffer = await message.bot.download_file(file.file_path)
        processed = image_service.safe_preprocess(buffer.read())

        ph = None
        try:
            ph = image_service.phash(processed)
        except Exception:
            logger.warning("pHash failed; skipping cache", exc_info=True)

        analysis = None
        if ph is not None:
            async with get_session() as session:
                analysis = await cache_service.lookup(session, ph)

        if analysis is None:
            analysis = await openai_service.analyze([processed])
            if ph is not None and analysis.get("candidates"):
                async with get_session() as session:
                    await cache_service.store(session, ph, analysis)
    except Exception:
        logger.exception("Failed to analyze photo")
        await status_msg.edit_text(t("image_error", lang))
        return

    await status_msg.delete()
    await _deliver_result(message, analysis, lang, "image")


@router.message(F.video)
async def handle_video(message: Message) -> None:
    video = message.video

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        lang = user.language
        is_admin = _is_admin(message.from_user.id)

        if not is_admin and is_file_too_large(video.file_size or 0):
            await message.answer(t("file_too_large_video", lang))
            return

        if not is_admin and not await can_search(session, user):
            await message.answer(t("limit_reached", lang, limit=FREE_DAILY_LIMIT))
            return

    status_msg = await message.answer(t("analyzing_video", lang))
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = os.path.join(tmp_dir, "video.mp4")
            file = await message.bot.get_file(video.file_id)
            await message.bot.download_file(file.file_path, destination=video_path)

            frame_paths = video_service.extract_frames(video_path, tmp_dir)
            raw_frames = []
            for frame_path in frame_paths:
                with open(frame_path, "rb") as f:
                    raw_frames.append(f.read())
            best_frames = image_service.select_best_frames(raw_frames, k=4)
            frames = [image_service.safe_preprocess(f) for f in best_frames]
            analysis = await openai_service.analyze(frames)
    except Exception:
        logger.exception("Failed to analyze video")
        await status_msg.edit_text(t("video_error", lang))
        return

    await status_msg.delete()
    await _deliver_result(message, analysis, lang, "video")


@router.message(F.text.regexp(VIDEO_LINK_PATTERN))
async def handle_video_link(message: Message) -> None:
    match = VIDEO_LINK_PATTERN.search(message.text)
    url = match.group(0)
    if not url.startswith("http"):
        url = f"https://{url}"
    source = "instagram" if INSTAGRAM_URL_PATTERN.search(url) else "youtube"

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        lang = user.language
        is_admin = _is_admin(message.from_user.id)

        if not is_admin and not await can_search(session, user):
            await message.answer(t("limit_reached", lang, limit=FREE_DAILY_LIMIT))
            return

    status_msg = await message.answer(t("analyzing_video", lang))
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            max_duration = ADMIN_MAX_LINK_DURATION_SEC if is_admin else video_service.MAX_LINK_VIDEO_DURATION_SEC
            video_path = await video_service.fetch_remote_video(url, tmp_dir, max_duration)

            await message.answer_video(FSInputFile(video_path))

            frame_paths = video_service.extract_frames(video_path, tmp_dir)
            raw_frames = []
            for frame_path in frame_paths:
                with open(frame_path, "rb") as f:
                    raw_frames.append(f.read())
            best_frames = image_service.select_best_frames(raw_frames, k=4)
            frames = [image_service.safe_preprocess(f) for f in best_frames]
            analysis = await openai_service.analyze(frames)
    except VideoTooLongError:
        await status_msg.edit_text(t("video_too_long", lang))
        return
    except Exception:
        logger.exception("Failed to fetch/analyze %s video", source)
        analysis = None
        if source == "youtube":
            try:
                thumbnail = await video_service.fetch_youtube_thumbnail(url)
                if thumbnail:
                    analysis = await openai_service.analyze([image_service.safe_preprocess(thumbnail)])
            except Exception:
                logger.exception("YouTube thumbnail fallback failed")
        if not analysis or not analysis.get("candidates"):
            await status_msg.edit_text(t("link_fetch_error", lang))
            return

    await status_msg.delete()
    await _deliver_result(message, analysis, lang, source)
