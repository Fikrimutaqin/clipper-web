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

    # Check for original clip or final rendered clip from Studio
    clip_path = CLIPS_DIR / f"{req.clip_id}.mp4"
    if not clip_path.exists():
        # Maybe it's a final render from the Studio
        final_path = CLIPS_DIR / f"final_{req.clip_id}.mp4"
        if final_path.exists():
            clip_path = final_path
        else:
            raise HTTPException(status_code=404, detail=f"File clip tidak ditemukan (ID: {req.clip_id})")

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

@router.post("/transcribe-clip/{clip_id}")
async def api_transcribe_clip_ai(clip_id: str):
    import google.generativeai as genai
    import json
    
    input_path = CLIPS_DIR / f"{clip_id}.mp4"
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Original clip tidak ditemukan")
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY tidak dikonfigurasi. Harap tambahkan di .env")
        
    try:
        genai.configure(api_key=api_key)
        # Uploading video strictly for processing audio
        uploaded = genai.upload_file(str(input_path))
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """Buat transkrip dari audio video ini beserta timestamp (start dan end dalam detik).
Tugasmu adalah membuat subtitle bahasa Indonesia.
Format HANYA keluarkan satu valid JSON array, di mana tiap objek berisi "start", "end", dan "text".
Contoh:
[ {"start": 0.0, "end": 2.5, "text": "kalimat pertama"}, {"start": 2.5, "end": 5.0, "text": "selanjutnya"} ]
"""
        response = model.generate_content([uploaded, prompt])
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
            
        entries = json.loads(text)
        
        # Cleanup uploaded file from google server to save space cache
        try:
            genai.delete_file(uploaded.name)
        except:
            pass
            
        return response_success(data={"entries": entries, "available": True}, message="Subtitles berhasil di-generate AI!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Transcribe Error: {str(e)}")


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

        try:
            # Cari subtitle file berdasarkan prefix task_id, bukan stem 'merged'
            sub_exts = [".vtt", ".srt"]
            sub_entries = []
            for ext in sub_exts:
                for candidate in DOWNLOADS_DIR.glob(f"dl_{task_id}_*{ext}"):
                    if candidate.exists():
                        content = candidate.read_text(encoding="utf-8", errors="ignore")
                        sub_entries = _parse_vtt(content, 0.0, duration or 99999.0)
                        break
                if sub_entries:
                    break
            
            if sub_entries:
                for seg in suggestions:
                    st = seg["start_seconds"]
                    en = seg["end_seconds"]
                    texts = [e["text"] for e in sub_entries if e["end"] >= st and e["start"] <= en]
                    full_text = " ".join(texts).strip()
                    if full_text:
                        score_data = _score_viral_moment(full_text, st, en)
                        seg["viral_score"] = max(seg.get("viral_score", 0), score_data["viral_score"]) # take the best of both audio & text
                        seg["type"] = score_data["type"]
                        seg["reason"] = score_data["reason"]
                        if "keywords_detected" in score_data:
                            seg["keywords_detected"] = score_data["keywords_detected"]
                
                # Re-sort heavily boosting text-based viral score segments
                suggestions.sort(key=lambda x: x.get("viral_score", 0), reverse=True)
        except Exception as sub_e:
            print("Error parsing subtitles for suggest:", sub_e)

        return response_success(
            data={"suggestions": suggestions, "duration": duration},
            message="Saran segment berhasil dibuat",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat saran: {str(e)}")


# ─── Viral Title Generator ────────────────────────────────────────────────────

import google.generativeai as genai
import json

def _generate_viral_titles_ai(video_title: str, format_type: str, context_text: str = "") -> list[dict]:
    # Fallback default hooks if AI fails
    short = (video_title or "Video")[:60]
    default_titles = [
        {"type": "emotion", "hook": "Speechless", "title": f"Momen Ini Bikin Semua Orang Speechless 😭 | {short}"},
        {"type": "punchline", "hook": "Plot Twist", "title": f"PLOT TWIST yang Gak Ada yang Expect dari '{short}' 😱"},
        {"type": "insight", "hook": "Secret Revealed", "title": f"Rahasia '{short}' yang Akhirnya Terungkap 🔥"}
    ]
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY tidak ditemukan, menggunakan fallback auto hook.")
        return default_titles

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        prompt = f"""Kamu adalah expert konten kreator spesialis video viral.
Buat 4 hook & judul Youtube/Tiktok viral berdasarkan konteks video ini.
Tipe video: {format_type} (short/vertical atau regular/horizontal).
Judul asli: {video_title}
Konteks teks dari subtitle:
{context_text[:1500] if context_text else 'Tidak ada subtitle, buat berdasarkan judul saja.'}

Pilih tipe hook yang sesuai: 'emotion', 'punchline', atau 'insight'.
Format output harus HANYA valid JSON string, berupa list of objects seperti ini:
[ {{"type": "emotion", "hook": "Wait For It", "title": "Tunggu Sampai Habis... Bikin Kaget \ud83e\udd2f"}}, ... ]
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        
        titles = json.loads(text)
        if isinstance(titles, list) and len(titles) > 0 and "title" in titles[0]:
            return titles
    except Exception as e:
        print(f"Error AI Title generation: {e}")
        pass
    
    return default_titles


@router.get("/title/{task_id}")
async def suggest_viral_title(task_id: str, format_type: str = "short", request: Request = None):
    """Generate viral title suggestions for a clip."""
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")

    video_title = task.get("video_title", "")
    youtube_id = task.get("youtube_id", "")

    # Coba extract teks subtitle untuk konteks AI
    context_text = ""
    try:
        sub_exts = [".vtt", ".srt"]
        for ext in sub_exts:
            for candidate in DOWNLOADS_DIR.glob(f"dl_{task_id}_*{ext}"):
                if candidate.exists():
                    sub_content = candidate.read_text(encoding="utf-8", errors="ignore")
                    entries = _parse_vtt(sub_content, 0.0, 99999.0)
                    context_text = " ".join([e["text"] for e in entries])
                    break
            if context_text: break
    except Exception:
        pass

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

    titles = await asyncio.to_thread(_generate_viral_titles_ai, video_title, format_type, context_text)
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

    # Search for subtitle files directly by matching the task_id
    sub_exts = [".vtt", ".srt"]
    for ext in sub_exts:
        for candidate in DOWNLOADS_DIR.glob(f"dl_{task_id}_*{ext}"):
            if candidate.exists():
                content = candidate.read_text(encoding="utf-8", errors="ignore")
                entries = _parse_vtt(content, float(start), float(end))
                return response_success(
                    data={"available": True, "entries": entries, "format": ext.lstrip(".")},
                    message=f"Subtitle ditemukan",
                )

    return response_success(
        data={"available": False, "entries": [], "format": None},
        message="Subtitle tidak tersedia. Video baru akan otomatis didownload subtitlenya.",
    )


# ─── Viral Moment Detector ────────────────────────────────────────────────────

# Keyword banks with per-word weight contributions (Indonesian + English)
_VIRAL_KEYWORDS: dict[str, tuple[int, str]] = {
    # --- HIGH IMPACT (emotion / shock) ---
    "gila":           (18, "emotion"),
    "parah":          (16, "emotion"),
    "gokil":          (16, "emotion"),
    "gilak":          (15, "emotion"),
    "serius":         (12, "emotion"),
    "serius?":        (12, "emotion"),
    "shocking":       (18, "emotion"),
    "syok":           (15, "emotion"),
    "kaget":          (14, "emotion"),
    "nangis":         (14, "emotion"),
    "ngerasa":        (10, "emotion"),
    "sedih":          (10, "emotion"),
    "marah":          (10, "emotion"),
    "kesel":          (10, "emotion"),
    "takut":          (10, "emotion"),
    "ngeri":          (12, "emotion"),
    "OMG":            (16, "emotion"),
    "omg":            (16, "emotion"),
    "wow":            (13, "emotion"),
    "WOW":            (13, "emotion"),
    "astaga":         (13, "emotion"),
    "gak nyangka":    (18, "emotion"),
    "tidak nyangka":  (18, "emotion"),
    "tidak disangka": (18, "emotion"),
    "impossible":     (15, "emotion"),
    "unbelievable":   (16, "emotion"),
    "bohong":         (12, "emotion"),
    "dusta":          (10, "emotion"),
    "speechless":     (15, "emotion"),
    # --- HOOK / ATTENTION GRABBERS ---
    "rahasia":            (18, "hook"),
    "secret":             (18, "hook"),
    "terungkap":          (18, "hook"),
    "finally revealed":   (18, "hook"),
    "revealed":           (14, "hook"),
    "ternyata":           (16, "hook"),
    "you won't believe":  (20, "hook"),
    "wait for it":        (16, "hook"),
    "plot twist":         (20, "hook"),
    "twist":              (14, "hook"),
    "ending":             (10, "hook"),
    "spoiler":            (10, "hook"),
    "eksklusif":          (14, "hook"),
    "exclusive":          (14, "hook"),
    "breaking":           (14, "hook"),
    "breaking news":      (18, "hook"),
    "terbaru":            (10, "hook"),
    "pertama kali":       (14, "hook"),
    "first time":         (14, "hook"),
    "viral":              (12, "hook"),
    "trending":           (12, "hook"),
    "bocoran":            (16, "hook"),
    "leaked":             (14, "hook"),
    "jangan bagikan":     (16, "hook"),
    "don't share":        (16, "hook"),
    # --- INSIGHT / VALUE ---
    "fakta":          (12, "insight"),
    "fact":           (12, "insight"),
    "tips":           (12, "insight"),
    "trik":           (12, "insight"),
    "trick":          (12, "insight"),
    "cara":           ( 8, "insight"),
    "bagaimana":      ( 6, "insight"),
    "how to":         (10, "insight"),
    "tutorial":       (10, "insight"),
    "penting":        (12, "insight"),
    "important":      (12, "insight"),
    "wajib tau":      (16, "insight"),
    "must know":      (16, "insight"),
    "terbukti":       (12, "insight"),
    "proven":         (12, "insight"),
    "riset":          (10, "insight"),
    "penelitian":     (10, "insight"),
    "studi":          (10, "insight"),
    "study":          (10, "insight"),
    "data":           ( 8, "insight"),
    "bukti":          (10, "insight"),
    "evidence":       (10, "insight"),
    "solusi":         (10, "insight"),
    "solution":       (10, "insight"),
    "strategi":       (10, "insight"),
    "strategy":       (10, "insight"),
    "rumus":          (10, "insight"),
    # --- PUNCHLINE / CLIMAX ---
    "pada akhirnya":  (12, "punchline"),
    "intinya":        (12, "punchline"),
    "kesimpulannya":  (12, "punchline"),
    "jadi":           ( 6, "punchline"),
    "akhirnya":       (12, "punchline"),
    "at the end":     (12, "punchline"),
    "turns out":      (14, "punchline"),
    "the truth is":   (14, "punchline"),
    "kenyataannya":   (14, "punchline"),
    "sebenernya":     (12, "punchline"),
    "sebenarnya":     (12, "punchline"),
    "actually":       (10, "punchline"),
    "hasilnya":       (10, "punchline"),
    "result":         ( 8, "punchline"),
    # --- CTA (Call to Action) ---
    "subscribe":      (12, "cta"),
    "like":           ( 8, "cta"),
    "komen":          ( 8, "cta"),
    "comment":        ( 8, "cta"),
    "share":          ( 8, "cta"),
    "follow":         ( 8, "cta"),
    "klik":           ( 6, "cta"),
    "click":          ( 6, "cta"),
    "tonton":         ( 6, "cta"),
    "watch":          ( 6, "cta"),
    "jangan lupa":    (10, "cta"),
    "don't forget":   (10, "cta"),
    "link di bio":    (10, "cta"),
    "link in bio":    (10, "cta"),
    "swipe up":       (10, "cta"),
    "kunjungi":       ( 6, "cta"),
    "visit":          ( 6, "cta"),
    "daftarkan":      ( 8, "cta"),
    "register":       ( 8, "cta"),
}

# Punctuation patterns that signal intensity / climax
_INTENSITY_PATTERNS = [
    (r"[!]{2,}", 8),          # Multiple exclamation marks
    (r"[?!]{2,}", 8),         # Mixed ?? or !?
    (r"\b[A-Z]{3,}\b", 6),   # All-caps word (e.g. WOW, OMG, GILA)
    (r"😱|🤯|😭|🔥|💥|⚡|❗|🚨", 8), # High-energy emojis
    (r"😂|😆|🤣|😹", 5),      # Humor emojis
    (r"\.{3,}", 3),            # Ellipsis → suspense
]


class ViralScoreRequest(BaseModel):
    subtitle_text: str
    start_time: float = 0.0
    end_time: float = 0.0


class ViralScoreBatchRequest(BaseModel):
    segments: list[ViralScoreRequest]


def _score_viral_moment(subtitle_text: str, start_time: float, end_time: float) -> dict:
    """
    Rule-based viral moment scorer.

    Returns a dict matching the prompt spec:
      viral_score (0-100), type, keywords_detected, reason
    """
    import re as _re

    text = subtitle_text.strip()
    text_lower = text.lower()

    if not text:
        return {
            "viral_score": 0,
            "type": "hook",
            "keywords_detected": [],
            "reason": "Segment kosong / tidak ada teks untuk dianalisis.",
        }

    raw_score = 0
    detected_keywords: list[str] = []
    type_votes: dict[str, int] = {
        "emotion": 0, "hook": 0, "insight": 0, "punchline": 0, "cta": 0
    }

    # ── 1. Keyword matching ──────────────────────────────────────────────────
    for kw, (weight, kw_type) in _VIRAL_KEYWORDS.items():
        if kw.lower() in text_lower:
            raw_score += weight
            type_votes[kw_type] += weight
            detected_keywords.append(kw)

    # ── 2. Intensity / punctuation patterns ─────────────────────────────────
    pattern_bonuses = 0
    for pattern, bonus in _INTENSITY_PATTERNS:
        if _re.search(pattern, text):
            pattern_bonuses += bonus
    raw_score += pattern_bonuses

    # ── 3. Duration factor: very short segments (<3 s) are penalised ────────
    duration = max(0.0, end_time - start_time)
    if duration < 3.0:
        raw_score = max(0, raw_score - 10)

    # ── 4. Length factor: extremely short texts (< 5 words) get penalty ────
    word_count = len(text.split())
    if word_count < 5:
        raw_score = max(0, raw_score - 8)

    # ── 5. Cap at 100 ───────────────────────────────────────────────────────
    viral_score = min(100, max(0, raw_score))

    # ── 6. Determine dominant type ──────────────────────────────────────────
    if any(v > 0 for v in type_votes.values()):
        dominant_type = max(type_votes, key=lambda t: type_votes[t])
    else:
        dominant_type = "hook"

    # ── 7. Build reason string ──────────────────────────────────────────────
    if viral_score >= 75:
        reason = (
            f"Segment ini sangat viral ({viral_score}/100). "
            f"Mengandung kata kunci high-impact: {', '.join(detected_keywords[:5])}. "
            f"Dominan tipe '{dominant_type}'."
        )
    elif viral_score >= 45:
        reason = (
            f"Potensi viral sedang ({viral_score}/100). "
            f"Terdapat beberapa elemen menarik: {', '.join(detected_keywords[:3]) or 'pola tanda baca'}. "
            f"Bisa dikembangkan lebih lanjut."
        )
    elif viral_score >= 20:
        reason = (
            f"Potensi viral rendah ({viral_score}/100). "
            + (f"Kata kunci lemah terdeteksi: {', '.join(detected_keywords)}. " if detected_keywords else "Tidak ada kata kunci kuat. ")
            + "Konten terkesan generik atau percakapan biasa."
        )
    else:
        reason = (
            f"Bukan momen viral ({viral_score}/100). "
            "Tidak ada kata kunci high-impact, emosi, atau hook yang terdeteksi. "
            "Kemungkinan filler atau percakapan biasa."
        )

    return {
        "viral_score": viral_score,
        "type": dominant_type,
        "keywords_detected": detected_keywords,
        "reason": reason,
    }


@router.post("/viral-score")
async def api_viral_score(req: ViralScoreRequest):
    """
    Analyze a subtitle segment and return a viral moment score.

    Input:
      - subtitle_text: the raw subtitle text
      - start_time: segment start in seconds
      - end_time:   segment end in seconds

    Output (JSON):
      - viral_score (0-100)
      - type: punchline | emotion | insight | hook | cta
      - keywords_detected: list of matched high-impact phrases
      - reason: short explanation
    """
    result = await asyncio.to_thread(
        _score_viral_moment,
        req.subtitle_text,
        req.start_time,
        req.end_time,
    )
    return response_success(data=result, message="Viral score berhasil dihitung")


@router.post("/viral-score/batch")
async def api_viral_score_batch(req: ViralScoreBatchRequest):
    """
    Score multiple subtitle segments in a single request.
    Returns each segment's score alongside its input timestamps.
    Segments are sorted by viral_score descending.
    """
    if not req.segments:
        raise HTTPException(status_code=400, detail="Segments tidak boleh kosong")
    if len(req.segments) > 200:
        raise HTTPException(status_code=400, detail="Maksimal 200 segments per request")

    async def _score_one(seg: ViralScoreRequest) -> dict:
        result = await asyncio.to_thread(
            _score_viral_moment,
            seg.subtitle_text,
            seg.start_time,
            seg.end_time,
        )
        return {
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "subtitle_text": seg.subtitle_text,
            **result,
        }

    scored = await asyncio.gather(*[_score_one(s) for s in req.segments])
    scored_sorted = sorted(scored, key=lambda x: x["viral_score"], reverse=True)

    return response_success(
        data={"results": scored_sorted, "total": len(scored_sorted)},
        message="Batch viral score berhasil dihitung",
    )
