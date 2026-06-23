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


def extract_frames(video_path: str, output_dir: str, timestamps: tuple[int, ...] = (0, 5, 10, 15)) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    frame_paths = []
    for i, ts in enumerate(timestamps, start=1):
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
    return frame_paths


def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _is_instagram_url(url: str) -> bool:
    return "instagram.com" in url


def _fetch_remote_video_sync(url: str, tmp_dir: str, max_duration: int) -> str:
    outtmpl = os.path.join(tmp_dir, "link_video.%(ext)s")
    ydl_opts = {
        "quiet": True,
        "noplaylist": True,
        "format": "mp4[height<=720]/best[height<=720]/best",
        "outtmpl": outtmpl,
        "remote_components": ["ejs:github"],
    }
    if _is_youtube_url(url) and YOUTUBE_COOKIES_FILE and os.path.exists(YOUTUBE_COOKIES_FILE):
        ydl_opts["cookiefile"] = YOUTUBE_COOKIES_FILE
    elif _is_instagram_url(url) and INSTAGRAM_COOKIES_FILE and os.path.exists(INSTAGRAM_COOKIES_FILE):
        ydl_opts["cookiefile"] = INSTAGRAM_COOKIES_FILE
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        duration = info.get("duration") or 0
        if duration > max_duration:
            raise VideoTooLongError(duration)
        ydl.download([url])

    for fname in os.listdir(tmp_dir):
        if fname.startswith("link_video."):
            return os.path.join(tmp_dir, fname)
    raise RuntimeError("Video download produced no file")


async def fetch_remote_video(url: str, tmp_dir: str, max_duration: int = MAX_LINK_VIDEO_DURATION_SEC) -> str:
    """Downloads a video from YouTube, Instagram (Reels/posts) or any other yt-dlp supported link."""
    return await asyncio.to_thread(_fetch_remote_video_sync, url, tmp_dir, max_duration)


def _fetch_youtube_thumbnail_sync(url: str) -> bytes | None:
    """Falls back to YouTube's public oEmbed thumbnail when yt-dlp gets bot-blocked.

    Thumbnails are served from plain image CDN URLs with no bot/cookie checks,
    so this keeps movie identification working even when full video download is blocked.
    """
    oembed = requests.get(
        "https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=10
    )
    oembed.raise_for_status()
    thumbnail_url = oembed.json().get("thumbnail_url")
    if not thumbnail_url:
        return None
    image = requests.get(thumbnail_url, timeout=10)
    image.raise_for_status()
    return image.content


async def fetch_youtube_thumbnail(url: str) -> bytes | None:
    return await asyncio.to_thread(_fetch_youtube_thumbnail_sync, url)
