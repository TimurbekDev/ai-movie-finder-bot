import asyncio
import glob
import logging
import os
import shutil

import ffmpeg
import requests
import yt_dlp

from config import INSTAGRAM_COOKIES_FILE, YOUTUBE_COOKIES_FILE

logger = logging.getLogger(__name__)

MAX_LINK_VIDEO_DURATION_SEC = 180


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
    return {
        "quiet": True,
        "noplaylist": True,
        "format": "mp4[height<=720]/best[height<=720]/best",
        "outtmpl": os.path.join(tmp_dir, "link_video.%(ext)s"),
        "remote_components": ["ejs:github"],
    }


def _attempt_download(url: str, ydl_opts: dict, tmp_dir: str, max_duration: int) -> tuple[str, str]:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get("duration") or 0
        if duration > max_duration:
            raise VideoTooLongError(duration)
        title = info.get("title") or ""
        ydl.download([url])

    for fname in os.listdir(tmp_dir):
        if fname.startswith("link_video.") and not fname.endswith((".part", ".ytdl")):
            return os.path.join(tmp_dir, fname), title
    raise RuntimeError("Video download produced no file")


def _fetch_remote_video_sync(url: str, tmp_dir: str, max_duration: int) -> tuple[str, str]:
    cookiefile = _cookiefile_for(url)

    attempts = [_base_opts(tmp_dir)]
    if _is_youtube_url(url):
        # TV/embedded player clients usually skip the "confirm you're not a bot"
        # sign-in wall that hits datacenter IPs on the default web client.
        attempts.append(
            {
                **_base_opts(tmp_dir),
                "extractor_args": {"youtube": {"player_client": ["tv", "web_embedded"]}},
            }
        )
    if cookiefile:
        for opts in attempts:
            opts["cookiefile"] = cookiefile

    last_err: Exception | None = None
    for i, ydl_opts in enumerate(attempts, start=1):
        try:
            return _attempt_download(url, ydl_opts, tmp_dir, max_duration)
        except VideoTooLongError:
            raise
        except Exception as e:
            last_err = e
            logger.warning("yt-dlp attempt %d/%d failed for %s: %s", i, len(attempts), url, e)
    raise last_err


async def fetch_remote_video(
    url: str, tmp_dir: str, max_duration: int = MAX_LINK_VIDEO_DURATION_SEC
) -> tuple[str, str]:
    """Download from YouTube/Instagram/any yt-dlp source -> (file path, video title)."""
    return await asyncio.to_thread(_fetch_remote_video_sync, url, tmp_dir, max_duration)


def _fetch_youtube_oembed_sync(url: str) -> tuple[str, bytes | None]:
    """Falls back to YouTube's public oEmbed data when yt-dlp gets bot-blocked.

    Thumbnails are served from plain image CDN URLs with no bot/cookie checks, and
    the video title often names the movie outright -- both feed the identifier
    even when full video download is blocked.
    """
    oembed = requests.get(
        "https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=10
    )
    oembed.raise_for_status()
    data = oembed.json()
    title = data.get("title") or ""

    thumbnail = None
    thumbnail_url = data.get("thumbnail_url")
    if thumbnail_url:
        image = requests.get(thumbnail_url, timeout=10)
        image.raise_for_status()
        thumbnail = image.content
    return title, thumbnail


async def fetch_youtube_oembed(url: str) -> tuple[str, bytes | None]:
    return await asyncio.to_thread(_fetch_youtube_oembed_sync, url)
