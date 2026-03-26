import asyncio
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import av
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from itsdangerous import BadSignature
from starlette.responses import FileResponse
from yt_dlp import YoutubeDL

from core import (
    CLIPS_DIR,
    DOWNLOADS_DIR,
    ROOT_DIR,
    UPLOADS_DIR,
    templates,
)
from core import ensure_dirs as _ensure_dirs
from core import get_or_create_sid as _get_or_create_sid
from core import set_sid_cookie as _set_sid_cookie
from db import create_job as _create_job
from db import get_google_token as _get_google_token
from db import get_job as _get_job
from db import init_db as _init_db
from db import list_jobs as _list_jobs
from db import update_job as _update_job
from db import upsert_session as _upsert_session
from google_auth import get_google_creds as _get_google_creds
from google_auth import google_flow as _google_flow
from google_auth import new_state, new_state_cookie_payload, read_oauth_state
from processing import parse_iso8601_duration as _parse_iso8601_duration
from processing import pyav_trim as _pyav_trim
from processing import suggest_segments_from_file as _suggest_segments_from_file

app = FastAPI()
app.mount("/assets", StaticFiles(directory=str(ROOT_DIR / "assets")), name="assets")


@app.on_event("startup")
async def _startup() -> None:
    """FastAPI startup hook to initialize directories and SQLite schema."""
    _ensure_dirs()
    _init_db()


def _download_youtube_to_uploads(*, url: str, job_id: str) -> Path:
    """Download a YouTube URL into uploads folder and return a local media path.

    This is best-effort and may fail with 403 due to YouTube protections.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    outtmpl = str(UPLOADS_DIR / f"{job_id}.%(format_id)s.%(ext)s")
    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "format": "bv*+ba/b",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "color": "never",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Referer": "https://www.youtube.com/",
        },
    }
    with YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except Exception as e:
            msg = str(e)
            if "HTTP Error 403" in msg or "403: Forbidden" in msg:
                raise RuntimeError(
                    "YouTube menolak proses download (403 Forbidden). "
                    "Biasanya ini terjadi karena proteksi YouTube atau pembatasan jaringan/server. "
                    "Coba video lain, atau gunakan mode upload file."
                )
            raise
        requested = info.get("requested_downloads") if isinstance(info, dict) else None

    filepaths: list[Path] = []
    if isinstance(requested, list):
        for d in requested:
            fp = (d or {}).get("filepath")
            if fp:
                p = Path(str(fp))
                if p.exists():
                    filepaths.append(p)

    if not filepaths and isinstance(info, dict):
        filename = YoutubeDL({"outtmpl": outtmpl}).prepare_filename(info)
        p = Path(filename)
        if p.exists():
            filepaths = [p]

    if len(filepaths) == 1:
        return filepaths[0]

    if not filepaths:
        for candidate in sorted(UPLOADS_DIR.glob(f"{job_id}.*")):
            if candidate.is_file():
                filepaths.append(candidate)

    def pick_stream_path(kind: str) -> Optional[Path]:
        """Pick the first downloaded file that contains the requested stream kind."""
        for p in filepaths:
            try:
                c = av.open(str(p))
                try:
                    if kind == "video" and any(s.type == "video" for s in c.streams):
                        return p
                    if kind == "audio" and any(s.type == "audio" for s in c.streams):
                        return p
                finally:
                    c.close()
            except Exception:
                continue
        return None

    video_path = pick_stream_path("video")
    audio_path = pick_stream_path("audio")
    if video_path and not audio_path:
        return video_path
    if not video_path:
        raise RuntimeError("Gagal menemukan stream video dari hasil unduhan")

    merged_path = UPLOADS_DIR / f"{job_id}.source.mkv"
    v_in = av.open(str(video_path))
    a_in = av.open(str(audio_path)) if audio_path else None
    try:
        v_stream = next((s for s in v_in.streams if s.type == "video"), None)
        if not v_stream:
            raise RuntimeError("Stream video tidak ditemukan")
        a_stream = None
        if a_in is not None:
            a_stream = next((s for s in a_in.streams if s.type == "audio"), None)

        out = av.open(str(merged_path), mode="w")
        try:
            out_v = out.add_stream(template=v_stream)
            out_a = out.add_stream(template=a_stream) if a_stream is not None else None

            for packet in v_in.demux(v_stream):
                if packet.dts is None:
                    continue
                packet.stream = out_v
                out.mux(packet)

            if a_in is not None and a_stream is not None and out_a is not None:
                for packet in a_in.demux(a_stream):
                    if packet.dts is None:
                        continue
                    packet.stream = out_a
                    out.mux(packet)
        finally:
            out.close()
    finally:
        v_in.close()
        if a_in is not None:
            a_in.close()

    if merged_path.exists():
        return merged_path

    raise RuntimeError("Gagal mengunduh video dari YouTube")


def _youtube_upload(
    *,
    sid: str,
    file_path: Path,
    title: str,
    description: str = "",
    format_type: str = "regular",
) -> str:
    """Upload an MP4 file to YouTube for the given session and return video id."""
    def build_metadata(raw_title: str, raw_description: str, fmt: str) -> tuple[str, str]:
        """Build a YouTube-safe title/description pair (handles length limits)."""
        base_title = (raw_title or "").strip()
        if not base_title:
            base_title = "Clipper Video"

        is_short = (fmt or "").strip().lower() == "short"
        suffix = ""
        max_len = 100
        if len(base_title) + len(suffix) > max_len:
            base_title = base_title[: max_len - len(suffix)].rstrip()
            if not base_title:
                base_title = "Clipper"
        final_title = f"{base_title}{suffix}"

        desc = (raw_description or "").strip()
        if not desc:
            desc = "Generated by Clipper.\n\n#Clipper"
        if len(desc) > 5000:
            desc = desc[:5000]

        return final_title, desc

    creds = _get_google_creds(sid)
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(str(file_path), mimetype="video/mp4", resumable=True)

    final_title, description = build_metadata(title, description, format_type)

    response = (
        youtube.videos()
        .insert(
            part="snippet,status",
            body={
                "snippet": {"title": final_title, "description": description},
                "status": {"privacyStatus": "public"},
            },
            media_body=media,
        )
        .execute()
    )
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("Upload YouTube gagal (tidak ada video id)")
    return str(video_id)


async def _process_job(job_id: str, sid: str) -> None:
    """Run the background job lifecycle: trim -> optional upload -> update status."""
    job = _get_job(job_id, sid)
    if not job:
        return

    try:
        _update_job(job_id, status="processing", error=None)
        input_path_value = str(job.get("input_path") or "")

        input_path = Path(input_path_value)
        if not input_path.exists():
            raise RuntimeError("File input tidak ditemukan")

        output_path = CLIPS_DIR / f"{job_id}.mp4"
        format_type = str(job.get("format_type", "regular"))
        
        _pyav_trim(
            input_path=input_path,
            output_path=output_path,
            start_seconds=float(job["start_seconds"]),
            end_seconds=float(job["end_seconds"]),
            format_type=format_type
        )
        _update_job(job_id, status="clipped", output_path=str(output_path))

        if int(job["upload_to_youtube"]) == 1:
            _update_job(job_id, status="uploading")
            video_id = await asyncio.to_thread(
                _youtube_upload,
                sid=sid,
                file_path=output_path,
                title=str(job["title"]),
                description=str(job.get("description") or ""),
                format_type=format_type,
            )
            _update_job(job_id, status="done", youtube_video_id=video_id)
        else:
            _update_job(job_id, status="done")
    except Exception as e:
        msg = str(e)
        if "HTTP Error 403" in msg or "403: Forbidden" in msg:
            msg = (
                "YouTube menolak proses download (403 Forbidden). "
                "Coba video lain, atau gunakan mode upload file."
            )
        _update_job(job_id, status="error", error=msg)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    """Render landing page (platform selection) and ensure a session cookie exists."""
    sid = _get_or_create_sid(request)
    token = _get_google_token(sid)
    if token:
        response = RedirectResponse(url="/dashboard")
        return _set_sid_cookie(response, sid)
    try:
        asset_version = int((ROOT_DIR / "assets" / "icon.png").stat().st_mtime)
    except Exception:
        asset_version = 1
    response = templates.TemplateResponse(
        "index.html", {"request": request, "asset_version": asset_version}
    )
    return _set_sid_cookie(response, sid)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main dashboard UI."""
    sid = _get_or_create_sid(request)
    token = _get_google_token(sid)
    if not token:
        response = RedirectResponse(url="/")
        return _set_sid_cookie(response, sid)
    jobs = _list_jobs(sid)
    try:
        asset_version = int((ROOT_DIR / "assets" / "icon.png").stat().st_mtime)
    except Exception:
        asset_version = 1
    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "is_connected": bool(token),
            "jobs": jobs,
            "asset_version": asset_version,
        },
    )
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.get("/auth/google/start")
async def google_start(request: Request) -> RedirectResponse:
    """Start Google OAuth flow and set state cookies."""
    sid = _get_or_create_sid(request)
    state = new_state()
    redirect_uri = str(request.url_for("google_callback"))
    flow = _google_flow(state=state, redirect_uri=redirect_uri)
    flow.redirect_uri = redirect_uri
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    response = RedirectResponse(url=authorization_url)
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    response.set_cookie("oauth_state", new_state_cookie_payload(state), httponly=True, samesite="lax")
    return response


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    """Handle OAuth callback, exchange code for tokens, and persist session tokens."""
    sid = _get_or_create_sid(request)
    payload = read_oauth_state(request)
    expected_state = payload.get("state")
    if not expected_state or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="State OAuth tidak valid")
    if not code:
        raise HTTPException(status_code=400, detail="Code OAuth tidak ditemukan")

    redirect_uri = str(request.url_for("google_callback"))
    flow = _google_flow(state=state, redirect_uri=redirect_uri)
    flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }
    _upsert_session(sid, token_data)
    response = RedirectResponse(url="/dashboard")
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    response.delete_cookie("oauth_state")
    return response


@app.get("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    """Disconnect the current Google/YouTube session for this sid."""
    sid = _get_or_create_sid(request)
    _upsert_session(sid, None)
    response = RedirectResponse(url="/")
    response.delete_cookie("oauth_state")
    return _set_sid_cookie(response, sid)


@app.get("/api/me")
async def api_me(request: Request) -> JSONResponse:
    """Return session info and connection status for the current user."""
    sid = _get_or_create_sid(request)
    token = _get_google_token(sid)
    return _set_sid_cookie(JSONResponse({"sid": sid, "is_connected": bool(token)}), sid)


@app.get("/api/youtube/videos")
async def api_youtube_videos(request: Request, limit: int = 25) -> JSONResponse:
    """List videos from the authenticated user's uploads playlist."""
    sid = _get_or_create_sid(request)
    required_scope = "https://www.googleapis.com/auth/youtube.readonly"
    token_data = _get_google_token(sid)
    if not token_data:
        raise HTTPException(status_code=401, detail="User belum menghubungkan akun Google/YouTube")
    scopes = token_data.get("scopes") or []
    if required_scope not in scopes:
        raise HTTPException(
            status_code=401,
            detail="Scope youtube.readonly belum diberikan, silakan Connect Google/YouTube ulang",
        )

    try:
        creds = _get_google_creds(sid)
        youtube = build("youtube", "v3", credentials=creds)
        channel_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
        items = channel_resp.get("items") or []
        if not items:
            return _set_sid_cookie(JSONResponse({"items": []}), sid)

        uploads_playlist_id = (
            (items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}
        ).get("uploads")
        if not uploads_playlist_id:
            return _set_sid_cookie(JSONResponse({"items": []}), sid)

        playlist_resp = (
            youtube.playlistItems()
            .list(part="snippet,contentDetails", playlistId=uploads_playlist_id, maxResults=limit)
            .execute()
        )
        videos: list[dict[str, Any]] = []
        for it in playlist_resp.get("items") or []:
            snippet = it.get("snippet") or {}
            content = it.get("contentDetails") or {}
            vid = content.get("videoId")
            if not vid:
                continue
            videos.append(
                {
                    "video_id": vid,
                    "title": snippet.get("title") or "",
                    "published_at": snippet.get("publishedAt") or "",
                    "thumbnail": (
                        ((snippet.get("thumbnails") or {}).get("default") or {}).get("url") or ""
                    ),
                }
            )

        return _set_sid_cookie(JSONResponse({"items": videos}), sid)
    except HttpError as e:
        status = int(getattr(getattr(e, "resp", None), "status", 500) or 500)
        if status in (401, 403):
            raise HTTPException(
                status_code=401,
                detail="Akses ditolak oleh YouTube API. Coba Connect ulang dan pastikan akun punya channel.",
            )
        raise HTTPException(status_code=502, detail="Gagal memuat video dari YouTube API")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal memuat video dari YouTube")

@app.get("/api/youtube/discover")
async def api_youtube_discover(
    request: Request,
    limit: int = 20,
    region: str = "ID",
) -> JSONResponse:
    """Discover YouTube videos for Indonesia (current strategy: podcast-focused search)."""
    sid = _get_or_create_sid(request)
    required_scope = "https://www.googleapis.com/auth/youtube.readonly"
    token_data = _get_google_token(sid)
    if not token_data:
        raise HTTPException(status_code=401, detail="User belum menghubungkan akun Google/YouTube")
    scopes = token_data.get("scopes") or []
    if required_scope not in scopes:
        raise HTTPException(
            status_code=401,
            detail="Scope youtube.readonly belum diberikan, silakan Connect Google/YouTube ulang",
        )

    max_results = max(1, min(int(limit or 20), 50))

    try:
        creds = _get_google_creds(sid)
        youtube = build("youtube", "v3", credentials=creds)

        # Karena kita mau mencari "Podcast" (yang spesifik), fitur chart="mostPopular" kurang cocok 
        # karena isinya campur aduk. Kita gunakan endpoint search biasa tapi diurutkan berdasarkan view/date terbaru
        
        published_after = datetime.now(timezone.utc) - timedelta(days=30)
        published_after_str = published_after.isoformat().replace("+00:00", "Z")

        search_resp = youtube.search().list(
            part="snippet",
            q="podcast indonesia",
            type="video",
            maxResults=max_results,
            order="viewCount",  # yang paling banyak ditonton dalam 30 hari terakhir
            publishedAfter=published_after_str,
            regionCode=(region or "ID")[:2].upper(),
            videoDuration="long", # podcast biasanya video panjang (> 20 menit)
        ).execute()
        
        ids: list[str] = []
        for it in search_resp.get("items") or []:
            vid = ((it.get("id") or {}).get("videoId") or "").strip()
            if vid:
                ids.append(vid)
                
        if not ids:
            return _set_sid_cookie(JSONResponse({"items": []}), sid)

        # Ambil durasi detail dari video IDs yang didapat
        videos_resp = (
            youtube.videos()
            .list(
                part="snippet,contentDetails,statistics",
                id=",".join(ids)
            )
            .execute()
        )
        
        items_out: list[dict[str, Any]] = []
        for v in videos_resp.get("items") or []:
            snippet = v.get("snippet") or {}
            content = v.get("contentDetails") or {}
            stats = v.get("statistics") or {}
            vid = (v.get("id") or "").strip()
            if not vid:
                continue
            
            # Kita tidak perlu mengecualikan musik secara manual lagi
            # karena query "podcast indonesia" sudah cukup terfilter
            items_out.append(
                {
                    "video_id": vid,
                    "title": snippet.get("title") or "",
                    "channel_title": snippet.get("channelTitle") or "",
                    "published_at": snippet.get("publishedAt") or "",
                    "thumbnail": (
                        ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url")
                        or ((snippet.get("thumbnails") or {}).get("default") or {}).get("url")
                        or ""
                    ),
                    "duration": _parse_iso8601_duration(content.get("duration")),
                    "view_count": stats.get("viewCount") or "",
                }
            )

        return _set_sid_cookie(JSONResponse({"items": items_out}), sid)
    except HttpError as e:
        status = int(getattr(getattr(e, "resp", None), "status", 500) or 500)
        if status in (401, 403):
            raise HTTPException(
                status_code=401,
                detail="Akses ditolak oleh YouTube API. Coba Connect ulang dan pastikan akun punya channel.",
            )
        raise HTTPException(status_code=502, detail="Gagal memuat video discovery dari YouTube API")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal memuat video discovery dari YouTube")


DOWNLOAD_TASKS: dict[str, dict[str, Any]] = {}

def _download_youtube_task(task_id: str, url: str):
    """Background download task that writes progress into DOWNLOAD_TASKS."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def progress_hook(d):
        """yt-dlp progress hook to update task progress percentage."""
        if d['status'] == 'downloading':
            p_str = d.get('_percent_str', '0%')
            p_str = ansi_escape.sub('', p_str).replace('%', '').strip()
            try:
                DOWNLOAD_TASKS[task_id]['progress'] = float(p_str)
            except Exception:
                pass
        elif d['status'] == 'finished':
            DOWNLOAD_TASKS[task_id]['progress'] = 100

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(DOWNLOADS_DIR / f"dl_{task_id}_%(id)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "nocheckcertificate": True,
        "no_warnings": True,
        "retries": 5,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
    }
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepaths: list[Path] = []
            reqs = info.get("requested_downloads") if isinstance(info, dict) else None
            if isinstance(reqs, list):
                for r in reqs:
                    fp = (r or {}).get("filepath")
                    if fp:
                        filepaths.append(Path(fp))
            if not filepaths:
                filepath = ydl.prepare_filename(info)
                filepaths.append(Path(filepath))

            filepath = filepaths[0]
            if len(filepaths) >= 2:
                v_path = filepaths[0]
                a_path = filepaths[1]
                merged_path = DOWNLOADS_DIR / f"dl_{task_id}_merged.mp4"
                v_in = av.open(str(v_path))
                a_in = av.open(str(a_path))
                out = av.open(str(merged_path), mode="w")
                try:
                    v_stream = next((s for s in v_in.streams if s.type == "video"), None)
                    a_stream = next((s for s in a_in.streams if s.type == "audio"), None)
                    if v_stream is None:
                        raise RuntimeError("Video stream tidak ditemukan saat merge download")
                    out_v = out.add_stream(template=v_stream)
                    out_a = out.add_stream(template=a_stream) if a_stream is not None else None
                    for packet in v_in.demux(v_stream):
                        if packet.dts is None:
                            continue
                        packet.stream = out_v
                        out.mux(packet)
                    if a_stream is not None and out_a is not None:
                        for packet in a_in.demux(a_stream):
                            if packet.dts is None:
                                continue
                            packet.stream = out_a
                            out.mux(packet)
                finally:
                    out.close()
                    v_in.close()
                    a_in.close()
                filepath = merged_path
            DOWNLOAD_TASKS[task_id]['status'] = 'done'
            DOWNLOAD_TASKS[task_id]['file_path'] = str(filepath)
    except Exception as e:
        DOWNLOAD_TASKS[task_id]['status'] = 'error'
        DOWNLOAD_TASKS[task_id]['error'] = str(e)

@app.post("/api/youtube/download")
async def api_youtube_download(request: Request, youtube_url: str = Form(...)) -> JSONResponse:
    """Create a download task for a YouTube URL and return a task id."""
    sid = _get_or_create_sid(request)
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {"status": "downloading", "progress": 0, "file_path": "", "error": ""}
    asyncio.create_task(asyncio.to_thread(_download_youtube_task, task_id, youtube_url))
    return _set_sid_cookie(JSONResponse({"task_id": task_id}), sid)

@app.get("/api/youtube/download/{task_id}")
async def api_youtube_download_status(request: Request, task_id: str) -> JSONResponse:
    """Return the current status/progress for a given download task id."""
    if task_id not in DOWNLOAD_TASKS:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return JSONResponse(DOWNLOAD_TASKS[task_id])

@app.get("/api/youtube/search")
async def api_youtube_search(
    request: Request,
    q: str = "",
    limit: int = 15,
) -> JSONResponse:
    """Search YouTube videos by keyword for the authenticated user."""
    sid = _get_or_create_sid(request)
    required_scope = "https://www.googleapis.com/auth/youtube.readonly"
    token_data = _get_google_token(sid)
    if not token_data:
        raise HTTPException(status_code=401, detail="User belum menghubungkan akun Google/YouTube")
    scopes = token_data.get("scopes") or []
    if required_scope not in scopes:
        raise HTTPException(
            status_code=401,
            detail="Scope youtube.readonly belum diberikan, silakan Connect Google/YouTube ulang",
        )

    q_val = (q or "").strip()
    if not q_val:
        return _set_sid_cookie(JSONResponse({"items": []}), sid)
    
    max_results = max(1, min(int(limit or 15), 25))

    try:
        creds = _get_google_creds(sid)
        youtube = build("youtube", "v3", credentials=creds)

        search_resp = youtube.search().list(
            part="snippet",
            q=q_val,
            type="video",
            maxResults=max_results,
            safeSearch="none",
            videoEmbeddable="true"
        ).execute()

        ids: list[str] = []
        for it in search_resp.get("items") or []:
            vid = ((it.get("id") or {}).get("videoId") or "").strip()
            if vid:
                ids.append(vid)
        if not ids:
            return _set_sid_cookie(JSONResponse({"items": []}), sid)

        videos_resp = (
            youtube.videos()
            .list(part="snippet,contentDetails,statistics", id=",".join(ids))
            .execute()
        )
        items_out: list[dict[str, Any]] = []
        for v in videos_resp.get("items") or []:
            snippet = v.get("snippet") or {}
            content = v.get("contentDetails") or {}
            stats = v.get("statistics") or {}
            vid = (v.get("id") or "").strip()
            if not vid:
                continue
            items_out.append(
                {
                    "video_id": vid,
                    "title": snippet.get("title") or "",
                    "channel_title": snippet.get("channelTitle") or "",
                    "published_at": snippet.get("publishedAt") or "",
                    "thumbnail": (
                        ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url")
                        or ((snippet.get("thumbnails") or {}).get("default") or {}).get("url")
                        or ""
                    ),
                    "duration": _parse_iso8601_duration(content.get("duration")),
                    "view_count": stats.get("viewCount") or "",
                }
            )

        return _set_sid_cookie(JSONResponse({"items": items_out}), sid)
    except HttpError as e:
        status = int(getattr(getattr(e, "resp", None), "status", 500) or 500)
        if status in (401, 403):
            raise HTTPException(
                status_code=401,
                detail="Akses ditolak oleh YouTube API. Coba Connect ulang dan pastikan akun punya channel.",
            )
        raise HTTPException(status_code=502, detail="Gagal mencari video dari YouTube API")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal mencari video dari YouTube")


@app.post("/api/suggest")
async def api_suggest(
    request: Request,
    video: Optional[UploadFile] = File(None),
    server_file: str = Form(""),
    target_seconds: float = Form(30.0),
) -> JSONResponse:
    """Return suggested clip timestamps for an uploaded file or a server-downloaded file."""
    sid = _get_or_create_sid(request)
    
    tmp_path: Optional[Path] = None
    try:
        if server_file and Path(server_file).exists():
            tmp_path = Path(server_file)
        else:
            if not video or not video.filename:
                raise HTTPException(status_code=400, detail="Pilih file video atau gunakan video yang sudah diunduh.")
            tmp_path = UPLOADS_DIR / f"suggest_{uuid.uuid4()}_{Path(video.filename).name}"
            with tmp_path.open("wb") as f:
                shutil.copyfileobj(video.file, f)

        candidates = await asyncio.to_thread(
            _suggest_segments_from_file, input_path=tmp_path, target_seconds=float(target_seconds)
        )
        return _set_sid_cookie(JSONResponse({"candidates": candidates}), sid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs")
async def api_create_job(
    request: Request,
    video: Optional[UploadFile] = File(None),
    server_file: str = Form(""),
    youtube_url: str = Form(""),
    start_seconds: float = Form(...),
    end_seconds: float = Form(...),
    title: str = Form("Clipper video"),
    description: str = Form(""),
    upload_to_youtube: bool = Form(False),
    format_type: str = Form("regular"),
) -> JSONResponse:
    """Create a new clipping job and start background processing."""
    sid = _get_or_create_sid(request)
    youtube_url = (youtube_url or "").strip()
    
    if server_file and Path(server_file).exists():
        input_path = Path(server_file)
    else:
        if not video or not video.filename:
            raise HTTPException(status_code=400, detail="Pilih file video atau gunakan video yang sudah diunduh.")
        input_path = UPLOADS_DIR / f"{uuid.uuid4()}_{Path(video.filename).name}"
        with input_path.open("wb") as f:
            shutil.copyfileobj(video.file, f)

    job_id = _create_job(
        sid=sid,
        input_path=str(input_path),
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        title=title,
        description=description,
        upload_to_youtube=bool(upload_to_youtube),
        source_type="youtube" if youtube_url or server_file else "upload",
        source_url=youtube_url or None,
        format_type=format_type,
    )

    asyncio.create_task(_process_job(job_id, sid))
    return _set_sid_cookie(JSONResponse({"job_id": job_id}), sid)

@app.get("/api/jobs/{job_id}")
async def api_get_job(request: Request, job_id: str) -> JSONResponse:
    """Return job status and download link (if available)."""
    sid = _get_or_create_sid(request)
    job = _get_job(job_id, sid)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    download_url = f"/clips/{job_id}.mp4" if job.get("output_path") else None
    return _set_sid_cookie(
        JSONResponse(
            {
                "id": job["id"],
                "status": job["status"],
                "error": job["error"],
                "title": job["title"],
                "download_url": download_url,
                "youtube_video_id": job["youtube_video_id"],
            }
        ),
        sid,
    )

@app.get("/clips/{job_id}.mp4")
async def clips(job_id: str, request: Request) -> FileResponse:
    """Serve a generated clip file for the current session."""
    sid = _get_or_create_sid(request)
    job = _get_job(job_id, sid)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan")
    output_path = job.get("output_path")
    if not output_path:
        raise HTTPException(status_code=404, detail="Clip belum tersedia")
    path = Path(str(output_path))
    if not path.exists():
        raise HTTPException(status_code=404, detail="File clip tidak ditemukan")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
