import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


DEMO_MODE = _bool("DEMO_MODE")

WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
WHOOP_REDIRECT_URI = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8000/auth/callback")
WHOOP_SCOPES = "offline read:profile read:body_measurement read:cycles read:recovery read:sleep read:workout"
WHOOP_API = "https://api.prod.whoop.com/developer"
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

WEB_URL = os.getenv("WEB_URL", "http://localhost:8000")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
COACH_MODEL = os.getenv("COACH_MODEL", "claude-sonnet-5-5")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")

DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Europe/Moscow")
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "fitproject.db"))

SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", "3600"))
