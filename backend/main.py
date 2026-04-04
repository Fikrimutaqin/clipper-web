from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from core import ensure_dirs, CLIPS_DIR
from _database.db import init_db
from routes import auth, jobs, marketplace, youtube, earnings
from google_auth import read_oauth_state
import os
import logging
import time
import json
from urllib.parse import parse_qs
from jose import jwt, JWTError

app = FastAPI(title="ClipFIX API", version="0.1.0")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("clipfix.api")

SENSITIVE_KEYS = {
    "password",
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "google_token",
    "google_token_json",
    "client_secret",
}

def _redact(value):
    if isinstance(value, dict):
        redacted = {}
        for k, v in value.items():
            if str(k).lower() in SENSITIVE_KEYS:
                redacted[k] = "***"
            else:
                redacted[k] = _redact(v)
        return redacted
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_write_requests(request, call_next):
    method = (request.method or "").upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)

    start = time.perf_counter()
    path = request.url.path

    user_id = None
    role = None
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, os.environ.get("CLIPPER_SECRET_KEY", "your-secret-key"), algorithms=["HS256"])
            user_id = payload.get("sub")
            role = payload.get("role")
        except JWTError:
            pass

    body_preview = None
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type or "application/x-www-form-urlencoded" in content_type:
        raw = await request.body()
        if raw:
            raw_text = raw[:2048].decode("utf-8", errors="replace")
            if "application/json" in content_type:
                try:
                    parsed = json.loads(raw_text)
                    body_preview = json.dumps(_redact(parsed), ensure_ascii=False)
                except Exception:
                    body_preview = raw_text
            else:
                try:
                    parsed = parse_qs(raw_text, keep_blank_values=True)
                    body_preview = json.dumps(_redact(parsed), ensure_ascii=False)
                except Exception:
                    body_preview = raw_text

    try:
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "write_request method=%s path=%s status=%s duration_ms=%s user_id=%s role=%s body=%s",
            method,
            path,
            getattr(response, "status_code", None),
            duration_ms,
            user_id,
            role,
            body_preview,
        )
        return response
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(
            "write_request_failed method=%s path=%s duration_ms=%s user_id=%s role=%s body=%s",
            method,
            path,
            duration_ms,
            user_id,
            role,
            body_preview,
        )
        raise

@app.on_event("startup")
async def startup_event():
    ensure_dirs()
    init_db()

@app.get("/")
async def root():
    return {"message": "Welcome to ClipFIX API", "status": "online"}

# Serve static files for clips
app.mount("/api/jobs/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")

# Include Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(marketplace.router, prefix="/api/marketplace", tags=["marketplace"])
app.include_router(earnings.router, prefix="/api/earnings", tags=["earnings"])

@app.get("/auth/google/callback")
async def google_callback_alias(request: Request, state: str = "", code: str = ""):
    payload = read_oauth_state(request)
    purpose = payload.get("purpose")
    if purpose == "auth":
        return await auth.handle_google_login_callback(request, state=state, code=code)
    return await youtube.handle_youtube_callback(request, state=state, code=code)
