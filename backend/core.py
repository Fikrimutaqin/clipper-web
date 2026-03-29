import os
import uuid
from pathlib import Path
from typing import Any, Optional
from pydantic_settings import BaseSettings
from jose import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from itsdangerous import URLSafeSerializer

ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
CLIPS_DIR = STORAGE_DIR / "clips"

load_dotenv(dotenv_path=ROOT_DIR / ".env")

class Settings(BaseSettings):
    secret_key: str = os.environ.get("CLIPPER_SECRET_KEY", "your-secret-key")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7 # 7 days
    
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.environ.get("GOOGLE_REDIRECT_URI", "")

settings = Settings()
serializer = URLSafeSerializer(settings.secret_key)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def ensure_dirs() -> None:
    """Create required storage directories (uploads/downloads/clips)."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

def response_success(data: Any = None, message: str = "Success", meta: Optional[dict] = None):
    return {
        "success": True,
        "message": message,
        "data": data,
        "meta": meta or {}
    }
