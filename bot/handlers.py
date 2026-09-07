import asyncio
import logging
import os
import re
import tempfile

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message, User as TgUser
from sqlalchemy import select

from bot import link_store
from bot.keyboards import (
    admin_panel_keyboard,
    language_keyboard,
    link_action_keyboard,
    main_menu_keyboard,
    movie_result_keyboard,
)
from config import ADMIN_IDS
from database.database import get_session
from database.models import SearchHistory
from services import cache_service, image_service, openai_service, verifier, video_service
from services.video_service import VideoTooLongError, YouTubeBlockedError
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
TG_CAPTION_LIMIT = 1024
# Bot API refuses uploads above this, and it rejects them only after the whole
# file has been pushed -- so check the size locally before sending.
TG_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024


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


def _prepare_video_frames(video_path: str, tmp_dir: str) -> tuple[list[bytes], int | None]:
    """CPU/subprocess-heavy frame pipeline; run via asyncio.to_thread only."""
    frame_paths = video_service.extract_frames(video_path, tmp_dir)
    raw_frames = []
    for frame_path in frame_paths:
        with open(frame_path, "rb") as f:
            raw_frames.append(f.read())
    best_frames = image_service.select_best_frames(raw_frames, k=4)
    frames = [image_service.safe_preprocess(f) for f in best_frames]
    ph = None
    if frames:
        try:
            ph = image_service.phash(frames[0])
        except Exception:
            logger.warning("pHash failed for video frame; skipping cache", exc_info=True)
    return frames, ph


async def _analyze_with_cache(frames: list[bytes], ph: int | None, hint: str = "") -> dict:
    """pHash cache in front of the vision call; miss or no-hash falls through to AI."""
    if ph is not None:
        async with get_session() as session:
            cached = await cache_service.lookup(session, ph)
        if cached is not None:
            return cached
    analysis = await openai_service.analyze(frames, ocr_text=hint)
    if ph is not None and analysis.get("candidates"):
        async with get_session() as session:
            await cache_service.store(session, ph, analysis)
    return analysis


async def _deliver_result(
    message: Message, from_user: TgUser, analysis: dict, lang: str, file_type: str
) -> None:
    """Resolve, persist and render the analysis.

    `message` is only a send target -- on the link flow it belongs to the bot, so
    the acting user is always passed explicitly.
    """
    candidates = analysis.get("candidates") or []
    tmdb_result = None
    if candidates:
        tmdb_result = await verifier.resolve(
            candidates, language=tmdb_language(lang), region=tmdb_region(lang)
        )

    async with get_session() as session:
        user = await get_or_create_user(
            session, from_user.id, from_user.username, from_user.language_code
        )
        await _save_history(session, user.id, file_type, analysis, tmdb_result)

    reply_text = _format_movie_reply(analysis, tmdb_result, lang)
    keyboard = movie_result_keyboard(
        tmdb_result.get("trailer") if tmdb_result else None,
        tmdb_result.get("watch_link") if tmdb_result else None,
        lang,
    )

    if tmdb_result and tmdb_result.get("poster"):
        caption = reply_text
        if len(caption) > TG_CAPTION_LIMIT:
            caption = caption[: TG_CAPTION_LIMIT - 1] + "…"
        try:
            await message.answer_photo(tmdb_result["poster"], caption=caption, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            logger.warning("Poster send failed; falling back to text", exc_info=True)
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
        raw = buffer.read()

        def _prepare() -> tuple[bytes, int | None]:
            processed = image_service.safe_preprocess(raw)
            try:
                return processed, image_service.phash(processed)
            except Exception:
                logger.warning("pHash failed; skipping cache", exc_info=True)
                return processed, None

        processed, ph = await asyncio.to_thread(_prepare)
        analysis = await _analyze_with_cache([processed], ph)
    except Exception:
        logger.exception("Failed to analyze photo")
        await status_msg.edit_text(t("image_error", lang))
        return

    await status_msg.delete()
    await _deliver_result(message, message.from_user, analysis, lang, "image")


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

            frames, ph = await asyncio.to_thread(_prepare_video_frames, video_path, tmp_dir)
            analysis = await _analyze_with_cache(frames, ph)
    except Exception:
        logger.exception("Failed to analyze video")
        await status_msg.edit_text(t("video_error", lang))
        return

    await status_msg.delete()
    await _deliver_result(message, message.from_user, analysis, lang, "video")


async def _identify_from_youtube_thumbnails(url: str) -> dict | None:
    """Identify from the thumbnail CDN when the player API bot-blocks the download.

    i.ytimg.com needs no auth and stays reachable from server IPs, and it exposes
    several distinct moments of the clip -- so this is a real multi-frame analysis,
    not a degraded single-image guess.
    """
    try:
        title, raw_frames = await video_service.fetch_youtube_frames(url)
        if not raw_frames:
            logger.warning("No YouTube thumbnails available for %s", url)
            return None

        def _prepare() -> tuple[list[bytes], int | None]:
            best = image_service.select_best_frames(raw_frames, k=4)
            frames = [image_service.safe_preprocess(f) for f in best]
            try:
                return frames, image_service.phash(frames[0])
            except Exception:
                return frames, None

        frames, ph = await asyncio.to_thread(_prepare)
        hint = f"Video title: {title}" if title else ""
        logger.info("YouTube thumbnail fallback: %d frame(s), title=%r", len(frames), title)
        return await _analyze_with_cache(frames, ph, hint=hint)
    except Exception:
        logger.exception("YouTube thumbnail fallback failed")
        return None


def _extract_link(text: str) -> str | None:
    match = VIDEO_LINK_PATTERN.search(text or "")
    if not match:
        return None
    url = match.group(0)
    return url if url.startswith("http") else f"https://{url}"


def _link_source(url: str) -> str:
    return "instagram" if INSTAGRAM_URL_PATTERN.search(url) else "youtube"


@router.message(F.text.regexp(VIDEO_LINK_PATTERN))
async def handle_video_link(message: Message) -> None:
    """A link alone is ambiguous, so ask what to do with it instead of guessing."""
    url = _extract_link(message.text)
    if not url:
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.language_code
        )
        lang = user.language

    token = link_store.put(url)
    await message.answer(t("link_action_prompt", lang), reply_markup=link_action_keyboard(token, lang))


@router.callback_query(F.data.startswith("link:"))
async def cb_link_action(callback: CallbackQuery) -> None:
    _, action, token = callback.data.split(":", 2)

    async with get_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.username, callback.from_user.language_code
        )
        lang = user.language
    is_admin = _is_admin(callback.from_user.id)

    url = link_store.get(token)
    if not url:
        await callback.message.edit_text(t("link_expired", lang))
        await callback.answer()
        return

    await callback.answer()
    if action == "video":
        await _download_link_video(callback, url, lang, is_admin)
    elif action == "audio":
        await _extract_link_audio(callback, url, lang, is_admin)
    else:
        await _identify_link_movie(callback, url, lang, is_admin)


async def _download_link_video(callback: CallbackQuery, url: str, lang: str, is_admin: bool) -> None:
    status_msg = await callback.message.edit_text(t("downloading_video", lang))
    max_duration = ADMIN_MAX_LINK_DURATION_SEC if is_admin else video_service.MAX_DOWNLOAD_DURATION_SEC
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path, title = await video_service.fetch_remote_video(url, tmp_dir, max_duration)
            if os.path.getsize(video_path) > TG_UPLOAD_LIMIT_BYTES:
                await status_msg.edit_text(t("file_too_large_to_send", lang))
                return
            await callback.message.answer_video(
                FSInputFile(video_path), caption=title[:TG_CAPTION_LIMIT] or None
            )
    except VideoTooLongError:
        await status_msg.edit_text(t("media_too_long", lang))
        return
    except YouTubeBlockedError:
        # No thumbnail fallback here -- the user asked for the file itself.
        logger.info("Download refused for %s: YouTube bot-check breaker open", url)
        await status_msg.edit_text(t("link_fetch_error", lang))
        return
    except Exception:
        logger.exception("Failed to download %s", url)
        await status_msg.edit_text(t("link_fetch_error", lang))
        return

    await status_msg.delete()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    return cleaned[:64] or "audio"


def _audio_performer(info: dict) -> str | None:
    for key in ("artist", "creator", "uploader", "channel"):
        value = info.get(key)
        if value:
            return str(value)[:64]
    return None


async def _extract_link_audio(callback: CallbackQuery, url: str, lang: str, is_admin: bool) -> None:
    status_msg = await callback.message.edit_text(t("extracting_audio", lang))
    max_duration = ADMIN_MAX_LINK_DURATION_SEC if is_admin else video_service.MAX_AUDIO_DURATION_SEC
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path, info = await video_service.fetch_remote_audio(url, tmp_dir, max_duration)
            if os.path.getsize(audio_path) > TG_UPLOAD_LIMIT_BYTES:
                await status_msg.edit_text(t("file_too_large_to_send", lang))
                return
            title = (info.get("track") or info.get("title") or "audio")[:64]
            await callback.message.answer_audio(
                FSInputFile(
                    audio_path, filename=f"{_safe_filename(title)}.{video_service.AUDIO_EXT}"
                ),
                title=title,
                performer=_audio_performer(info),
                duration=int(info.get("duration") or 0) or None,
            )
    except VideoTooLongError:
        await status_msg.edit_text(t("media_too_long", lang))
        return
    except Exception:
        # Includes YouTubeBlockedError: thumbnails carry no audio, so there is no fallback.
        logger.exception("Failed to extract audio from %s", url)
        await status_msg.edit_text(t("audio_error", lang))
        return

    await status_msg.delete()


async def _identify_link_movie(callback: CallbackQuery, url: str, lang: str, is_admin: bool) -> None:
    source = _link_source(url)

    if not is_admin:
        async with get_session() as session:
            user = await get_or_create_user(
                session, callback.from_user.id, callback.from_user.username, callback.from_user.language_code
            )
            if not await can_search(session, user):
                await callback.message.edit_text(t("limit_reached", lang, limit=FREE_DAILY_LIMIT))
                return

    status_msg = await callback.message.edit_text(t("analyzing_video", lang))
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            max_duration = ADMIN_MAX_LINK_DURATION_SEC if is_admin else video_service.MAX_LINK_VIDEO_DURATION_SEC
            video_path, video_title = await video_service.fetch_remote_video(url, tmp_dir, max_duration)

            frames, ph = await asyncio.to_thread(_prepare_video_frames, video_path, tmp_dir)
            hint = f"Video title: {video_title}" if video_title else ""
            analysis = await _analyze_with_cache(frames, ph, hint=hint)
    except VideoTooLongError:
        await status_msg.edit_text(t("video_too_long", lang))
        return
    except YouTubeBlockedError:
        logger.info("Skipping yt-dlp for %s (breaker open); using thumbnails", url)
        analysis = await _identify_from_youtube_thumbnails(url)
        if not analysis or not analysis.get("candidates"):
            await status_msg.edit_text(t("link_fetch_error", lang))
            return
    except Exception:
        logger.exception("Failed to fetch/analyze %s video", source)
        analysis = None
        if source == "youtube":
            analysis = await _identify_from_youtube_thumbnails(url)
        if not analysis or not analysis.get("candidates"):
            await status_msg.edit_text(t("link_fetch_error", lang))
            return

    await status_msg.delete()
    await _deliver_result(callback.message, callback.from_user, analysis, lang, source)
