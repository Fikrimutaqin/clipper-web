from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import asyncio
import uuid
import av
from google_auth import get_google_creds, google_flow, new_state, read_oauth_state
from googleapiclient.discovery import build
from services.job_service import _download_youtube_task, DOWNLOAD_TASKS, _youtube_upload
from _database.db import get_google_token, upsert_session
from core import response_success, CLIPS_DIR, serializer, settings
from processing import pyav_trim, suggest_segments_from_file
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

router = APIRouter()

class TrimRequest(BaseModel):
    task_id: str
    start_seconds: float
    end_seconds: float
    format_type: str = "regular" # regular or short

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
async def api_youtube_download(url: str):
    cleaned = (url or "").strip().strip("`").strip().strip('"').strip("'")
    if not cleaned:
        raise HTTPException(status_code=400, detail="URL YouTube harus diisi")
    
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {"status": "downloading", "progress": 0, "url": cleaned}
    
    # Run download in background
    asyncio.create_task(asyncio.to_thread(_download_youtube_task, task_id, cleaned))
    
    return response_success(data={"task_id": task_id}, message="Download dimulai")

@router.get("/download/{task_id}")
async def api_youtube_download_status(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return response_success(data=task)

@router.post("/trim")
async def api_youtube_trim(req: TrimRequest, request: Request):
    task = DOWNLOAD_TASKS.get(req.task_id)
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

@router.get("/suggest/{task_id}")
async def api_youtube_suggest(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Video belum selesai didownload atau tidak ditemukan")
    
    input_path = Path(task["file_path"])
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="File video tidak ditemukan di server")

    try:
        # Get metadata for duration check
        with av.open(str(input_path)) as container:
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            
        suggestions = await asyncio.to_thread(
            suggest_segments_from_file,
            input_path=input_path,
            target_seconds=60.0 # Default suggestion duration
        )
        
        return response_success(
            data={
                "suggestions": suggestions,
                "duration": duration
            },
            message="Saran segment berhasil dibuat"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat saran: {str(e)}")
