import asyncio
import glob
import hashlib
import importlib.util
import logging
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import ffmpeg
import requests
import yt_dlp

from config import INSTAGRAM_COOKIES_FILE, POT_PROVIDER_URL, YOUTUBE_COOKIES_FILE, YTDLP_PROXY

logger = logging.getLogger(__name__)

MAX_LINK_VIDEO_DURATION_SEC = 180

_session = requests.Session()  # keep-alive for thumbnail/oEmbed fetches


def _ensure_ffmpeg_on_path() -> None:
    """Picks up a freshly winget-installed ffmpeg before a shell restart refreshes PATH."""
    if shutil.which("ffmpeg"):
        return
    pattern = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\ffmpeg.exe")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        os.environ["PATH"] = os.path.dirname(matches[0]) + os.pathsep + os.environ["PATH"]


_ensure_ffmpeg_on_path()


class VideoTooLongError(Exception):
    pass


class YouTubeBlockedError(Exception):
    """Raised without hitting the network while the bot-check breaker is open."""


# YouTube bot-checks whole server IPs, not individual videos, so once it refuses
# every further attempt burns ~4s to fail identically. One request already probes
# several player clients, so a single all-attempts-blocked request is conclusive:
# trip immediately and serve from thumbnails instead.
#
# Matches ONLY the IP-level bot message -- "Sign in to confirm your age" is a
# per-video restriction and must not trip the breaker.
_BOT_BLOCK_RE = re.compile(r"confirm you'?re not a bot", re.IGNORECASE)
_YT_COOLDOWN_BASE_SEC = 5 * 60
_YT_COOLDOWN_MAX_SEC = 60 * 60
_yt_block_streak = 0
_yt_breaker_until = 0.0


def _yt_breaker_open() -> bool:
    return time.monotonic() < _yt_breaker_until


def _record_yt_outcome(blocked: bool) -> None:
    """Trip on the first blocked request; back off exponentially while it persists.

    Fast to trip so users never pay for doomed attempts, but short at first so a
    transient block recovers in minutes rather than staying stuck for an hour.
    """
    global _yt_block_streak, _yt_breaker_until
    if not blocked:
        if _yt_block_streak or _yt_breaker_until:
            logger.info("YouTube downloads working again; bot-check breaker reset")
        _yt_block_streak, _yt_breaker_until = 0, 0.0
        return

    _yt_block_streak += 1
    cooldown = min(_YT_COOLDOWN_BASE_SEC * 2 ** (_yt_block_streak - 1), _YT_COOLDOWN_MAX_SEC)
    _yt_breaker_until = time.monotonic() + cooldown
    logger.warning(
        "YouTube bot-check (block #%d); skipping yt-dlp for %d min, using thumbnails",
        _yt_block_streak,
        cooldown // 60,
    )


def _video_duration(video_path: str) -> float:
    try:
        return float(ffmpeg.probe(video_path)["format"]["duration"])
    except Exception:
        logger.warning("ffprobe failed for %s; falling back to blind seeks", video_path)
        return 0.0


def _sample_timestamps(duration: float, max_frames: int) -> list[float]:
    """Evenly spaced seeks across the clip, avoiding intro/outro edges."""
    if duration <= 0:
        # Unknown duration: probe a few early offsets blindly (skip 0s -> often black/logo).
        return [1.0, 3.0, 6.0, 10.0, 15.0, 21.0]
    if duration <= 2:
        return [0.0, max(duration - 0.2, 0.1)]
    start = max(1.0, duration * 0.05)
    end = duration * 0.95
    n = max(4, min(max_frames, int(duration / 3)))
    step = (end - start) / max(n - 1, 1)
    return [round(start + i * step, 2) for i in range(n)]


def extract_frames(video_path: str, output_dir: str, max_frames: int = 10) -> list[str]:
    """Sample candidate frames spread over the whole clip.

    The caller narrows these down with image_service.select_best_frames; seeks
    past the clip end simply yield no frame and are skipped.
    """
    os.makedirs(output_dir, exist_ok=True)
    duration = _video_duration(video_path)
    frame_paths = []
    for i, ts in enumerate(_sample_timestamps(duration, max_frames), start=1):
        out_path = os.path.join(output_dir, f"frame{i}.jpg")
        try:
            (
                ffmpeg.input(video_path, ss=ts)
                .output(out_path, vframes=1)
                .overwrite_output()
                .run(quiet=True)
            )
            if os.path.exists(out_path):
                frame_paths.append(out_path)
        except ffmpeg.Error:
            logger.exception("Failed to extract frame at %ss", ts)

    if not frame_paths:  # last resort: very first frame
        out_path = os.path.join(output_dir, "frame0.jpg")
        try:
            ffmpeg.input(video_path).output(out_path, vframes=1).overwrite_output().run(quiet=True)
            if os.path.exists(out_path):
                frame_paths.append(out_path)
        except ffmpeg.Error:
            logger.exception("Failed to extract fallback frame")
    return frame_paths


def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _is_instagram_url(url: str) -> bool:
    return "instagram.com" in url


def _cookiefile_for(url: str) -> str | None:
    if _is_youtube_url(url) and YOUTUBE_COOKIES_FILE and os.path.exists(YOUTUBE_COOKIES_FILE):
        return YOUTUBE_COOKIES_FILE
    if _is_instagram_url(url) and INSTAGRAM_COOKIES_FILE and os.path.exists(INSTAGRAM_COOKIES_FILE):
        return INSTAGRAM_COOKIES_FILE
    return None


def _base_opts(tmp_dir: str) -> dict:
    opts = {
        "quiet": True,
        "noplaylist": True,
        "format": "mp4[height<=720]/best[height<=720]/best",
        "outtmpl": os.path.join(tmp_dir, "link_video.%(ext)s"),
        "remote_components": ["ejs:github"],
        "extractor_args": {},
    }
    if POT_PROVIDER_URL:
        # bgutil sidecar mints PO tokens -> YouTube accepts datacenter IPs without cookies
        opts["extractor_args"]["youtubepot-bgutilhttp"] = {"base_url": [POT_PROVIDER_URL]}
    if YTDLP_PROXY:
        opts["proxy"] = YTDLP_PROXY
    return opts


_pot_diag_logged = False


def _pot_diagnostics() -> str:
    """One-line state of the PO-token setup, for log forensics on bot-block."""
    try:
        spec = importlib.util.find_spec("yt_dlp_plugins.extractor.getpot_bgutil_http")
    except Exception:
        spec = None
    plugin = "installed" if spec else "MISSING (add bgutil-ytdlp-pot-provider to the image)"
    if not POT_PROVIDER_URL:
        provider = "POT_PROVIDER_URL not set"
    else:
        try:
            r = requests.get(f"{POT_PROVIDER_URL.rstrip('/')}/ping", timeout=5)
            provider = f"{POT_PROVIDER_URL} ping={r.status_code}"
        except Exception as e:
            provider = f"{POT_PROVIDER_URL} UNREACHABLE ({type(e).__name__})"
    proxy = "on" if YTDLP_PROXY else "off"
    return f"yt-dlp={yt_dlp.version.__version__} plugin={plugin} provider={provider} proxy={proxy}"


def _log_pot_diag_once() -> None:
    global _pot_diag_logged
    if not _pot_diag_logged:
        _pot_diag_logged = True
        logger.info("PO-token status: %s", _pot_diagnostics())


def _attempt_download(url: str, ydl_opts: dict, tmp_dir: str, max_duration: int) -> tuple[str, str]:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get("duration") or 0
        if duration > max_duration:
            raise VideoTooLongError(duration)
        title = info.get("title") or ""
        # Reuse the already-extracted info: ydl.download() would re-run the whole
        # (bot-check-prone) extraction against YouTube a second time.
        ydl.process_ie_result(info, download=True)

    for fname in os.listdir(tmp_dir):
        if fname.startswith("link_video.") and not fname.endswith((".part", ".ytdl")):
            return os.path.join(tmp_dir, fname), title
    raise RuntimeError("Video download produced no file")


def _fetch_remote_video_sync(url: str, tmp_dir: str, max_duration: int) -> tuple[str, str]:
    _log_pot_diag_once()
    is_youtube = _is_youtube_url(url)
    if is_youtube and _yt_breaker_open():
        raise YouTubeBlockedError("bot-check breaker open; skipping yt-dlp")

    cookiefile = _cookiefile_for(url)

    if is_youtube:
        # Cookie-less first: stale cookies poison requests, and alternative player
        # clients (tv / embedded / android_vr) skip the sign-in bot wall that hits
        # datacenter IPs on the default web client. Cookies are the last resort.
        alt = _base_opts(tmp_dir)
        alt["extractor_args"]["youtube"] = {"player_client": ["tv", "web_embedded", "android_vr"]}
        attempts = [_base_opts(tmp_dir), alt]
        if cookiefile:
            with_cookies = _base_opts(tmp_dir)
            with_cookies["cookiefile"] = cookiefile
            attempts.append(with_cookies)
    else:
        opts = _base_opts(tmp_dir)
        if cookiefile:
            opts["cookiefile"] = cookiefile
        attempts = [opts]

    last_err: Exception | None = None
    for i, ydl_opts in enumerate(attempts, start=1):
        try:
            result = _attempt_download(url, ydl_opts, tmp_dir, max_duration)
            if is_youtube:
                _record_yt_outcome(blocked=False)
            return result
        except VideoTooLongError:
            raise
        except Exception as e:
            last_err = e
            logger.warning("yt-dlp attempt %d/%d failed for %s: %s", i, len(attempts), url, e)

    if is_youtube:
        blocked = bool(_BOT_BLOCK_RE.search(str(last_err)))
        _record_yt_outcome(blocked)
        if blocked:
            # Expected on server IPs; the thumbnail path handles it. Raising the raw
            # DownloadError here would dump a traceback for a condition we recover from.
            raise YouTubeBlockedError(str(last_err)) from last_err
    logger.error("All yt-dlp attempts failed for %s. PO-token status: %s", url, _pot_diagnostics())
    raise last_err


async def fetch_remote_video(
    url: str, tmp_dir: str, max_duration: int = MAX_LINK_VIDEO_DURATION_SEC
) -> tuple[str, str]:
    """Download from YouTube/Instagram/any yt-dlp source -> (file path, video title)."""
    return await asyncio.to_thread(_fetch_remote_video_sync, url, tmp_dir, max_duration)


_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:shorts/|embed/|live/|watch\?(?:.*&)?v=)|youtu\.be/)([\w-]{11})"
)

# i.ytimg.com serves these off a plain image CDN with no bot check, so they stay
# reachable from datacenter IPs that the player API rejects. Several are genuinely
# different moments of the clip, not just crops of one thumbnail.
_THUMB_NAMES = ("oar2", "maxresdefault", "frame0", "hq1", "hq2", "hq3", "hqdefault")


def youtube_video_id(url: str) -> str | None:
    match = _YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def _fetch_youtube_title_sync(url: str) -> str:
    """oEmbed title -- often names the movie outright, and needs no auth."""
    try:
        resp = _session.get(
            "https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("title") or ""
    except Exception:
        logger.warning("YouTube oEmbed title fetch failed for %s", url, exc_info=True)
        return ""


def _fetch_thumb(video_id: str, name: str) -> bytes | None:
    try:
        resp = _session.get(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg", timeout=10)
        if resp.status_code != 200 or not resp.content:
            return None
        return resp.content
    except Exception:
        return None


def _fetch_youtube_frames_sync(url: str) -> tuple[str, list[bytes]]:
    """Title + distinct still frames pulled straight from the thumbnail CDN.

    This is the path that keeps identification working when the player API answers
    "Sign in to confirm you're not a bot" -- as of 2026 PO tokens no longer clear
    that check from server IPs, but the image CDN never enforced it.
    """
    video_id = youtube_video_id(url)
    if not video_id:
        return _fetch_youtube_title_sync(url), []

    with ThreadPoolExecutor(max_workers=8) as pool:
        title_future = pool.submit(_fetch_youtube_title_sync, url)
        images = list(pool.map(lambda n: _fetch_thumb(video_id, n), _THUMB_NAMES))
        title = title_future.result()

    frames, seen = [], set()
    for img in images:
        if not img:
            continue
        digest = hashlib.md5(img).digest()  # several names alias the same picture
        if digest in seen:
            continue
        seen.add(digest)
        frames.append(img)
    return title, frames


async def fetch_youtube_frames(url: str) -> tuple[str, list[bytes]]:
    return await asyncio.to_thread(_fetch_youtube_frames_sync, url)
