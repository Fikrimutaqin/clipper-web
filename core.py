import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Request
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer

ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
CLIPS_DIR = STORAGE_DIR / "clips"
DB_PATH = STORAGE_DIR / "app.db"

load_dotenv(dotenv_path=ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    secret_key: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    @staticmethod
    def from_env() -> "Settings":
        """Load app settings from environment variables with safe defaults."""
        secret_key = os.environ.get("CLIPPER_SECRET_KEY", "")
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        google_redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "")
        if not secret_key:
            secret_key = secrets.token_urlsafe(32)
        return Settings(
            secret_key=secret_key,
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_redirect_uri=google_redirect_uri,
        )


settings = Settings.from_env()
serializer = URLSafeSerializer(settings.secret_key, salt="clipper-web")
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


def ensure_dirs() -> None:
    """Create required storage directories (uploads/downloads/clips)."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_sid(request: Request) -> str:
    """Get the current session id from cookies, or generate a new one."""
    sid = request.cookies.get("sid")
    if sid:
        return sid
    return str(uuid.uuid4())


def set_sid_cookie(response: Any, sid: str) -> Any:
    """Attach the session id cookie to a response."""
    try:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    except Exception:
        pass
    return response
