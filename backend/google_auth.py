import os
import secrets
from typing import Any

# Allow insecure transport for local development (OAuth over http://)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from fastapi import HTTPException, Request
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature

from core import serializer, settings
from db import get_google_token, upsert_session


def get_google_creds(sid: str) -> Credentials:
    """Build and refresh Google OAuth credentials for a given session id."""
    token_data = get_google_token(sid)
    if not token_data:
        raise RuntimeError("User belum menghubungkan akun Google/YouTube")

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            token_data["access_token"] = creds.token
            if creds.refresh_token:
                token_data["refresh_token"] = creds.refresh_token
            upsert_session(sid, token_data)
        else:
            raise RuntimeError("Token Google tidak valid, silakan connect ulang")

    return creds


def google_flow(*, state: str, redirect_uri: str) -> Flow:
    """Create an OAuth Flow instance with the app scopes and redirect URIs."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500, detail="GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET belum diset"
        )
    redirect_uris = [redirect_uri]
    if settings.google_redirect_uri and settings.google_redirect_uri not in redirect_uris:
        redirect_uris.append(settings.google_redirect_uri)
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": redirect_uris,
            }
        },
        scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ],
        state=state,
    )


def read_oauth_state(request: Request) -> dict[str, Any]:
    """Read and validate OAuth state payload from cookies."""
    raw_state = request.cookies.get("oauth_state", "")
    try:
        payload = serializer.loads(raw_state) if raw_state else {}
    except BadSignature:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def new_state_cookie_payload(state: str) -> str:
    """Serialize an OAuth state payload for storage in a cookie."""
    return serializer.dumps({"state": state})


def new_state() -> str:
    """Generate a cryptographically secure OAuth state string."""
    return secrets.token_urlsafe(16)
