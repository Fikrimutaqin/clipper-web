from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import asyncio
import re
import os
import uuid
import av
from google_auth import get_google_creds, google_flow, new_state, read_oauth_state
from googleapiclient.discovery import build
from services.job_service import _download_youtube_task, DOWNLOAD_TASKS, _youtube_upload
from _database.db import get_google_token, upsert_session
from core import response_success, CLIPS_DIR, DOWNLOADS_DIR, serializer, settings
from processing import pyav_trim, suggest_segments_from_file, extract_frame_jpeg, render_video_with_template
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

_UUID_RE = re.compile(
    r'^dl_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
)

router = APIRouter()


def _recover_task(task_id: str) -> dict | None:
    """
    Return a task dict for task_id.
    If not in DOWNLOAD_TASKS (e.g. after server restart), scan DOWNLOADS_DIR
    to find the video file and auto-register the task.
    """
    task = DOWNLOAD_TASKS.get(task_id)
    if task and task.get("status") == "done":
        return task

    # Try merged file first, then any matching mp4
    candidates = [DOWNLOADS_DIR / f"dl_{task_id}_merged.mp4"]
    candidates += list(DOWNLOADS_DIR.glob(f"dl_{task_id}_*.mp4"))
    for path in candidates:
        if path.exists() and path.suffix == ".mp4":
            recovered = {"status": "done", "progress": 100, "file_path": str(path)}
            DOWNLOAD_TASKS[task_id] = recovered
            return recovered

    # Return in-progress task (downloading/error) as-is so status polling still works
    return task

class TrimRequest(BaseModel):
    task_id: str
    start_seconds: float
    end_seconds: float
    format_type: str = "short"  # short atau regular

class DownloadRequest(BaseModel):
    url: str

class UploadClipRequest(BaseModel):
    clip_id: str
    title: str
    description: Optional[str] = None
    format_type: str = "regular"

@router.get("/status")
async def youtube_status(request: Request):
    sid = request.cookies.get("sid")
    if not sid:
        return response_success(data={"connected": False})
    token = get_google_token(sid)
    return response_success(data={"connected": bool(token)})

@router.get("/connect")
async def youtube_connect(request: Request, redirect: str = "/dashboard/clipper"):
    sid = request.cookies.get("sid") or str(uuid.uuid4())
    upsert_session(sid, None)

    state = new_state()
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    referer_origin = ""
    if referer:
        try:
            rp = urlparse(referer)
            if rp.scheme and rp.netloc:
                referer_origin = f"{rp.scheme}://{rp.netloc}"
        except Exception:
            referer_origin = ""
    safe_redirect = "/dashboard/clipper"
    if redirect.startswith("/"):
        safe_redirect = redirect
    else:
        try:
            parsed = urlparse(redirect)
            if parsed.scheme in {"http", "https"}:
                if origin and redirect.startswith(origin):
                    safe_redirect = redirect
                elif referer_origin and redirect.startswith(referer_origin):
                    safe_redirect = redirect
                elif parsed.netloc == "localhost:3000":
                    safe_redirect = redirect
        except Exception:
            safe_redirect = "/dashboard/clipper"

    oauth_state = serializer.dumps({"state": state, "redirect": safe_redirect, "purpose": "youtube"})

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = settings.google_redirect_uri or f"{base_url}/api/youtube/callback"
    flow = google_flow(state=state, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    resp.set_cookie("oauth_state", oauth_state, httponly=True, samesite="lax")
    return resp

async def handle_youtube_callback(request: Request, state: str = "", code: str = ""):
    sid = request.cookies.get("sid")
    if not sid:
        raise HTTPException(status_code=400, detail="Sesi tidak ditemukan")

    payload = read_oauth_state(request)
    expected_state = payload.get("state")
    redirect_url = payload.get("redirect") or "/dashboard/clipper"
    if not expected_state or not state or state != expected_state:
        raise HTTPException(status_code=400, detail="OAuth state tidak valid")
    if not code:
        raise HTTPException(status_code=400, detail="OAuth code tidak ditemukan")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = settings.google_redirect_uri or f"{base_url}/api/youtube/callback"
    flow = google_flow(state=state, redirect_uri=redirect_uri)
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
    upsert_session(sid, token_data)

    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    resp.set_cookie("oauth_state", "", httponly=True, samesite="lax")
    return resp

@router.get("/callback")
async def youtube_callback(request: Request, state: str = "", code: str = ""):
    return await handle_youtube_callback(request, state=state, code=code)

@router.post("/upload-clip")
async def youtube_upload_clip(req: UploadClipRequest, request: Request):
    sid = request.cookies.get("sid")
    if not sid:
        raise HTTPException(status_code=401, detail="Sesi tidak ditemukan, silakan connect YouTube dulu")

    clip_path = CLIPS_DIR / f"{req.clip_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="File clip tidak ditemukan")

    if req.format_type not in {"regular", "short"}:
        raise HTTPException(status_code=400, detail="Format tidak valid (regular atau short)")

    try:
        video_id = await asyncio.to_thread(
            _youtube_upload,
            sid=sid,
            file_path=clip_path,
            title=req.title,
            description=req.description or "",
            format_type=req.format_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return response_success(
        message="Upload ke YouTube berhasil",
        data={
            "youtube_video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        },
    )

@router.get("/discover")
async def api_youtube_discover(
    region: str = "ID", 
    limit: int = 20, 
    request: Request = None,
):
    sid = request.cookies.get("sid")
    if not sid:
        raise HTTPException(status_code=401, detail="Sesi tidak ditemukan")
    
    try:
        creds = get_google_creds(sid)
        youtube = build("youtube", "v3", credentials=creds)
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            chart="mostPopular",
            regionCode=region,
            maxResults=limit
        ).execute()
        return response_success(data=response)
    except Exception as e:
        if "401" in str(e):
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search")
async def api_youtube_search(
    q: str,
    region: str = "ID",
    limit: int = 20,
    request: Request = None,
):
    sid = request.cookies.get("sid")
    if not sid:
        raise HTTPException(status_code=401, detail="Sesi tidak ditemukan")
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query pencarian harus diisi")

    try:
        creds = get_google_creds(sid)
        youtube = build("youtube", "v3", credentials=creds)
        search_res = youtube.search().list(
            part="snippet",
            q=q.strip(),
            type="video",
            maxResults=limit,
            regionCode=region,
        ).execute()

        video_ids = []
        for item in search_res.get("items", []):
            vid = (item.get("id") or {}).get("videoId")
            if vid:
                video_ids.append(vid)

        if not video_ids:
            return response_success(data={"items": [], "pageInfo": {"totalResults": 0, "resultsPerPage": 0}})

        videos_res = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(video_ids),
            maxResults=min(limit, 50),
        ).execute()

        return response_success(data=videos_res)
    except Exception as e:
        if "401" in str(e):
            raise HTTPException(status_code=401, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download")
async def api_youtube_download(req: DownloadRequest):
    cleaned = (req.url or "").strip().strip("`").strip().strip('"').strip("'")
    if not cleaned:
        raise HTTPException(status_code=400, detail="URL YouTube harus diisi")
    
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {"status": "downloading", "progress": 0, "url": cleaned}
    
    # Run download in background
    asyncio.create_task(asyncio.to_thread(_download_youtube_task, task_id, cleaned))
    
    return response_success(data={"task_id": task_id}, message="Download dimulai")

@router.get("/download/{task_id}")
async def api_youtube_download_status(task_id: str):
    task = _recover_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return response_success(data=task)

@router.post("/trim")
async def api_youtube_trim(req: TrimRequest, request: Request):
    task = _recover_task(req.task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Video belum selesai didownload atau tidak ditemukan")
    
    input_path = Path(task["file_path"])
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="File video tidak ditemukan di server")

    if req.start_seconds < 0:
        raise HTTPException(status_code=400, detail="Start time tidak boleh kurang dari 0")
    if req.end_seconds <= req.start_seconds:
        raise HTTPException(status_code=400, detail="End time harus lebih besar dari start time")
    if req.format_type not in {"regular", "short"}:
        raise HTTPException(status_code=400, detail="Format tidak valid (regular atau short)")

    try:
        with av.open(str(input_path)) as container:
            duration = float(container.duration / av.time_base) if container.duration else None
    except Exception:
        duration = None

    if duration is not None and req.end_seconds > duration:
        raise HTTPException(status_code=400, detail="End time melebihi durasi video")

    clip_duration = req.end_seconds - req.start_seconds
    min_duration = 600.0 if req.format_type == "regular" else 20.0
    if clip_duration < min_duration:
        label = "10 menit" if req.format_type == "regular" else "20 detik"
        raise HTTPException(
            status_code=400,
            detail=f"Durasi clip ({int(clip_duration)}s) kurang dari minimum {label} untuk format {req.format_type}."
        )

    clip_id = str(uuid.uuid4())
    output_path = CLIPS_DIR / f"{clip_id}.mp4"
    
    try:
        # Run trimming in background thread since it's CPU intensive
        await asyncio.to_thread(
            pyav_trim,
            input_path=input_path,
            output_path=output_path,
            start_seconds=req.start_seconds,
            end_seconds=req.end_seconds,
            format_type=req.format_type
        )
        
        clip_path = f"/api/jobs/clips/{clip_id}.mp4"
        base_url = str(request.base_url).rstrip("/")
        return response_success(
            data={
                "clip_id": clip_id,
                "url": clip_path,
                "full_url": f"{base_url}{clip_path}",
                "duration": duration
            },
            message="Video berhasil di-clip"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses clip: {str(e)}")

class SubtitleEntry(BaseModel):
    start: float
    end: float
    text: str

class TemplateConfigModel(BaseModel):
    fontname: str = "Montserrat"
    fontsize: str = "60"
    primary_colour: str = "FFFFFF"
    outline_colour: str = "000000"
    outline: int = 4
    shadow: int = 1
    alignment: int = 2
    margin_v: int = 200
    uppercase: bool = True
    entries: list[SubtitleEntry] = []

class RenderRequest(BaseModel):
    clip_id: str
    template: TemplateConfigModel

@router.post("/render-template")
async def api_render_template(req: RenderRequest, request: Request):
    input_path = CLIPS_DIR / f"{req.clip_id}.mp4"
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Original clip tidak ditemukan")
        
    # Buat filename final_xxx untuk membedakan dengan klip sumber textless
    final_clip_id = f"final_{req.clip_id}"
    output_path = CLIPS_DIR / f"{final_clip_id}.mp4"
    
    try:
        await asyncio.to_thread(
            render_video_with_template,
            input_video=str(input_path),
            output_video=str(output_path),
            template_config=req.template.dict()
        )
        
        clip_path = f"/api/jobs/clips/{final_clip_id}.mp4"
        base_url = str(request.base_url).rstrip("/")
        return response_success(
            data={
                "clip_id": final_clip_id,
                "url": clip_path,
                "full_url": f"{base_url}{clip_path}"
            },
            message="Video berhasil di-render dengan template styling."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal merender template: {str(e)}")

@router.get("/suggest/{task_id}")
async def api_youtube_suggest(task_id: str, format_type: str = "short"):
    task = _recover_task(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Video belum selesai didownload atau tidak ditemukan")

    input_path = Path(task["file_path"])
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="File video tidak ditemukan di server")

    try:
        with av.open(str(input_path)) as container:
            duration = float(container.duration / av.time_base) if container.duration else 0.0

        target = 60.0 if format_type == "short" else 600.0
        suggestions = await asyncio.to_thread(
            suggest_segments_from_file,
            input_path=input_path,
            target_seconds=target,
            format_type=format_type,
        )
        return response_success(
            data={"suggestions": suggestions, "duration": duration},
            message="Saran segment berhasil dibuat",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat saran: {str(e)}")


# ─── Viral Title Generator ────────────────────────────────────────────────────

def _generate_viral_titles(video_title: str, format_type: str) -> list[dict]:
    short = (video_title or "Video")[:60]
    is_short = format_type == "short"
    titles = [
        # Emotion
        {"type": "emotion", "hook": "Speechless",
         "title": f"Momen Ini Bikin Semua Orang Speechless 😭 | {short}"},
        {"type": "emotion", "hook": "Viral Moment",
         "title": f"Kenapa Momen Ini Bisa Bikin Jutaan Orang Nangis? | {short}"},
        # Punchline
        {"type": "punchline", "hook": "Plot Twist",
         "title": f"PLOT TWIST yang Gak Ada yang Expect dari '{short}' 😱"},
        {"type": "punchline", "hook": "Wait For It",
         "title": f"Tunggu Sampai Habis... Ending '{short}' Bikin Kaget 🤯"},
        # Insight
        {"type": "insight", "hook": "Secret Revealed",
         "title": f"Rahasia '{short}' yang Akhirnya Terungkap 🔥"},
        {"type": "insight", "hook": "Must Know",
         "title": f"Fakta Penting dari {short} yang Wajib Kamu Tau!"},
    ]
    if is_short:
        titles += [
            {"type": "emotion", "hook": "POV",
             "title": f"POV: Kamu Nonton {short} & Langsung Shocked 😭 #shorts"},
            {"type": "punchline", "hook": "Trending",
             "title": f"Gak Nyangka Ini Bisa Terjadi 🤯 | {short} #shorts #viral"},
            {"type": "insight", "hook": "Hidden Truth",
             "title": f"Hal Ini yang Gak Pernah Diberitahu | {short} #shorts"},
        ]
    return titles


@router.get("/title/{task_id}")
async def suggest_viral_title(task_id: str, format_type: str = "short", request: Request = None):
    """Generate viral title suggestions for a clip."""
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")

    video_title = task.get("video_title", "")
    youtube_id = task.get("youtube_id", "")

    # Try to fetch real title from YouTube API if not stored
    if not video_title and youtube_id and request:
        sid = request.cookies.get("sid")
        if sid:
            try:
                creds = get_google_creds(sid)
                yt_api = build("youtube", "v3", credentials=creds)
                resp = yt_api.videos().list(part="snippet", id=youtube_id).execute()
                items = resp.get("items", [])
                if items:
                    video_title = items[0]["snippet"]["title"]
                    task["video_title"] = video_title
            except Exception:
                pass

    titles = _generate_viral_titles(video_title, format_type)
    return response_success(
        message="Saran judul viral berhasil dibuat",
        data={"titles": titles, "video_title": video_title},
    )


# ─── Thumbnail Extractor ──────────────────────────────────────────────────────

@router.get("/thumbnail/{task_id}")
async def get_thumbnail(task_id: str, at: float = 0.0):
    """Extract a JPEG thumbnail from a downloaded video at timestamp `at` seconds."""
    from fastapi.responses import Response

    # Validate task_id format to prevent path traversal
    if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', task_id):
        raise HTTPException(status_code=400, detail="task_id tidak valid")

    task = DOWNLOAD_TASKS.get(task_id)

    # Auto-recover from disk if not in memory (server restart case)
    if not task or task.get("status") != "done":
        found_path: Path | None = None
        # Prefer merged file, then any mp4 matching the task_id
        merged = DOWNLOADS_DIR / f"dl_{task_id}_merged.mp4"
        if merged.exists():
            found_path = merged
        else:
            for f in DOWNLOADS_DIR.glob(f"dl_{task_id}_*.mp4"):
                found_path = f
                break
        if found_path:
            DOWNLOAD_TASKS[task_id] = {"status": "done", "progress": 100, "file_path": str(found_path)}
            task = DOWNLOAD_TASKS[task_id]

    if not task or task.get("status") != "done":
        raise HTTPException(status_code=404, detail="Video belum selesai didownload atau task tidak ditemukan")

    input_path = Path(task["file_path"])
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="File video tidak ditemukan di server")

    try:
        jpeg_bytes = await asyncio.to_thread(extract_frame_jpeg, input_path, max(0.0, at))
        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil thumbnail: {str(e)}")


# ─── Media Library ────────────────────────────────────────────────────────────

@router.get("/media")
async def list_media():
    """List all downloaded video files in the downloads directory."""
    media_items = []

    try:
        files = sorted(
            DOWNLOADS_DIR.glob("dl_*.mp4"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        files = []

    for file_path in files:
        match = _UUID_RE.match(file_path.name)
        if not match:
            continue
        task_id = match.group(1)

        stat = file_path.stat()
        size_bytes = stat.st_size
        created_at = stat.st_mtime

        # Read duration via PyAV
        duration_seconds: Optional[float] = None
        try:
            with av.open(str(file_path)) as container:
                if container.duration:
                    duration_seconds = float(container.duration / av.time_base)
        except Exception:
            pass

        # Extract YouTube video id from filename when possible
        # Pattern: dl_{task_id}_{youtube_id}.mp4  OR  dl_{task_id}_merged.mp4
        name_without_ext = file_path.stem          # e.g. "dl_{uuid}_{ytid}"
        suffix = name_without_ext[len(f"dl_{task_id}_"):] if name_without_ext.startswith(f"dl_{task_id}_") else ""
        youtube_id = None if suffix == "merged" else (suffix or None)

        # Re-register into DOWNLOAD_TASKS so clipper can use it without re-download
        if task_id not in DOWNLOAD_TASKS or DOWNLOAD_TASKS[task_id].get("status") != "done":
            DOWNLOAD_TASKS[task_id] = {
                "status": "done",
                "progress": 100,
                "file_path": str(file_path),
                "url": f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else "",
            }

        media_items.append({
            "task_id": task_id,
            "filename": file_path.name,
            "youtube_id": youtube_id,
            "size_bytes": size_bytes,
            "duration_seconds": duration_seconds,
            "created_at": created_at,
        })

    return response_success(
        message="Media library berhasil diambil",
        data=media_items,
        meta={"total": len(media_items)},
    )

@router.get("/media/clips")
async def list_clips(request: Request):
    """List all user-generated clips in the clips directory."""
    clip_items = []
    try:
        files = sorted(
            CLIPS_DIR.glob("*.mp4"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        files = []

    base_url = str(request.base_url).rstrip("/")
    for file_path in files:
        clip_id = file_path.stem
        stat = file_path.stat()

        duration_seconds: Optional[float] = None
        try:
            with av.open(str(file_path)) as container:
                if container.duration:
                    duration_seconds = float(container.duration / av.time_base)
        except Exception:
            pass

        clip_items.append({
            "clip_id": clip_id,
            "filename": file_path.name,
            "size_bytes": stat.st_size,
            "duration_seconds": duration_seconds,
            "created_at": stat.st_mtime,
            "url": f"/api/jobs/clips/{file_path.name}",
            "full_url": f"{base_url}/api/jobs/clips/{file_path.name}"
        })

    return response_success(data=clip_items)

@router.delete("/media/clips/{clip_filename}")
async def delete_clip(clip_filename: str):
    """Delete a specific clip file from the clips directory."""
    if not clip_filename.endswith(".mp4") or "/" in clip_filename or "\\" in clip_filename:
        raise HTTPException(status_code=400, detail="Filename tidak valid")
        
    file_path = CLIPS_DIR / clip_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File clip tidak ditemukan")
        
    try:
        file_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghapus klip: {str(e)}")
        
    return response_success(message="Klip berhasil dihapus")



@router.delete("/media/{task_id}")
async def delete_media(task_id: str):
    """Delete all downloaded files for a given task_id."""
    # Validate task_id is a UUID to prevent path traversal
    if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', task_id):
        raise HTTPException(status_code=400, detail="task_id tidak valid")

    deleted: list[str] = []
    try:
        for f in DOWNLOADS_DIR.glob(f"dl_{task_id}_*"):
            f.unlink(missing_ok=True)
            deleted.append(f.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghapus file: {str(e)}")

    DOWNLOAD_TASKS.pop(task_id, None)

    return response_success(
        message=f"{len(deleted)} file berhasil dihapus",
        data={"deleted_files": deleted},
    )


# ─── Subtitle Discovery ───────────────────────────────────────────────────────

def _parse_vtt(content: str, start_sec: float, end_sec: float) -> list[dict]:
    """Parse WebVTT or SRT and return entries within [start_sec, end_sec]."""
    import re as _re

    def ts_to_sec(ts: str) -> float:
        parts = ts.replace(",", ".").split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])

    arrow_re = _re.compile(
        r"(\d{1,2}:\d{2}[:.]\d{2,3})\s*-->\s*(\d{1,2}:\d{2}[:.]\d{2,3})"
    )
    entries: list[dict] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        m = arrow_re.match(lines[i].strip())
        if m:
            t_start = ts_to_sec(m.group(1))
            t_end = ts_to_sec(m.group(2))
            i += 1
            text_parts: list[str] = []
            while i < len(lines) and lines[i].strip():
                cleaned = _re.sub(r"<[^>]+>", "", lines[i]).strip()
                if cleaned:
                    text_parts.append(cleaned)
                i += 1
            text = " ".join(text_parts)
            if text and t_end >= start_sec and t_start <= end_sec:
                entries.append({
                    "start": round(t_start - start_sec, 2),
                    "end": round(t_end - start_sec, 2),
                    "text": text,
                })
        else:
            i += 1
    return entries


@router.get("/subtitles/{task_id}")
async def get_subtitles(task_id: str, start: float = 0.0, end: float = 9999.0):
    """Return parsed subtitle entries within [start, end] seconds for a downloaded video."""
    if not re.fullmatch(r'[0-9a-f-]{36}', task_id):
        raise HTTPException(400, "task_id tidak valid")

    task = DOWNLOAD_TASKS.get(task_id)
    # Auto-recover from disk
    if not task:
        for f in DOWNLOADS_DIR.glob(f"dl_{task_id}_*.mp4"):
            task = {"status": "done", "progress": 100, "file_path": str(f)}
            DOWNLOAD_TASKS[task_id] = task
            break
        merged = DOWNLOADS_DIR / f"dl_{task_id}_merged.mp4"
        if merged.exists():
            task = {"status": "done", "progress": 100, "file_path": str(merged)}
            DOWNLOAD_TASKS[task_id] = task

    if not task:
        raise HTTPException(404, "Task tidak ditemukan")

    vid_path = Path(task.get("file_path", ""))
    stem = vid_path.stem if vid_path.exists() else f"dl_{task_id}"

    # Search for subtitle files with common extensions
    sub_exts = [".en.vtt", ".id.vtt", ".vtt", ".en.srt", ".id.srt", ".srt"]
    for ext in sub_exts:
        candidate = DOWNLOADS_DIR / f"{stem}{ext}"
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8", errors="ignore")
            entries = _parse_vtt(content, float(start), float(end))
            return response_success(
                data={"available": True, "entries": entries, "format": ext.lstrip(".")},
                message=f"Subtitle ditemukan ({ext})",
            )

    return response_success(
        data={"available": False, "entries": [], "format": None},
        message="Subtitle tidak tersedia. Video baru akan otomatis didownload subtitlenya.",
    )
