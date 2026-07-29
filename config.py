import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "")
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "")
# bgutil-ytdlp-pot-provider sidecar; empty = disabled
POT_PROVIDER_URL = os.getenv("POT_PROVIDER_URL", "")
# Residential/mobile proxy for yt-dlp. YouTube bot-checks datacenter IPs regardless
# of client or PO token, so this is the only way to restore full video download.
YTDLP_PROXY = os.getenv("YTDLP_PROXY", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")
