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

# Global imports with graceful fallback for "minim budget" environments
try:
    import google.generativeai as genai
except ImportError:
    genai = None

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

class RenderRequest(BaseModel):
    clip_id: str
    template: dict

class RenderBatchRequest(BaseModel):
    clip_ids: list[str]
    template: dict

class UploadClipRequest(BaseModel):
    clip_id: str
    title: str
    description: Optional[str] = None
    format_type: str = "regular"

class BatchProcessRequest(BaseModel):
    format_type: str = "short"
    samples: int = 10


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

@router.post("/transcribe-clip/{clip_id}")
async def api_transcribe_clip_ai(clip_id: str):
    import json
    
    if genai is None:
        raise HTTPException(status_code=400, detail="Metode AI Transcribe tidak tersedia karena library google-generativeai belum diinstal. Harap gunakan transkrip lokal atau instal dependensi.")

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
            template_config=req.template
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

@router.post("/render-batch")
async def api_render_batch(req: RenderBatchRequest, request: Request):
    """Render multiple clips with the SAME template styling in one operation."""
    sem = asyncio.Semaphore(4) # Limit parallel FFmpeg renders to 4 to avoid CPU melt
    
    async def _render_one(cid: str):
        async with sem:
            input_path = CLIPS_DIR / f"{cid}.mp4"
            if not input_path.exists(): return {"id": cid, "status": "error", "reason": "Clip not found"}
            
            final_id = f"final_{cid}"
            output_p = CLIPS_DIR / f"{final_id}.mp4"
            
            try:
                await asyncio.to_thread(
                    render_video_with_template,
                    input_video=str(input_path),
                    output_video=str(output_p),
                    template_config=req.template
                )
                return {"id": cid, "final_id": final_id, "status": "done", "url": f"/api/jobs/clips/{final_id}.mp4"}
            except Exception as e:
                return {"id": cid, "status": "error", "reason": str(e)}

    results = await asyncio.gather(*[_render_one(cid) for cid in req.clip_ids])
    return response_success(data={"results": results}, message=f"{len([r for r in results if r['status'] == 'done'])} clips rendered successfully!")

@router.post("/upload-batch")
async def api_upload_batch(req: list[UploadClipRequest], request: Request):
    """Upload multiple clips sequentially to YouTube Shorts/Video."""
    sid = request.cookies.get("sid")
    if not sid: raise HTTPException(status_code=401, detail="Harap login YouTube terlebih dahulu")
    
    results = []
    # Sequentially to avoid YouTube quota/rate-limit issues
    for up_req in req:
        # Check if it's a final_xxx clip or normal
        cid = up_req.clip_id
        input_path = CLIPS_DIR / f"{cid}.mp4"
        if not input_path.exists():
            results.append({"id": cid, "status": "error", "reason": "Clip file missing"})
            continue
            
        try:
            # Re-implement a small piece of _youtube_upload logic or call it
            # For simplicity, we trigger the existing task system or do it directly
            res_id = await asyncio.to_thread(
                _youtube_upload,
                sid=sid,
                file_path=str(input_path),
                title=up_req.title,
                description=up_req.description or "Automatically uploaded by ClipFIX AI",
                format_type=up_req.format_type
            )
            results.append({"id": cid, "status": "done", "video_id": res_id})
        except Exception as e:
            results.append({"id": cid, "status": "error", "reason": str(e)})

    return response_success(data={"results": results}, message=f"{len([r for r in results if r['status'] == 'done'])} clips uploaded!")

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
        # Get baseline highlights from audio energy
        suggestions = await asyncio.to_thread(
            suggest_segments_from_file,
            input_path=input_path,
            target_seconds=target,
            format_type=format_type,
        )

        try:
            # Look for subtitle files
            sub_exts = [".vtt", ".srt"]
            sub_entries = []
            for ext in sub_exts:
                for candidate in DOWNLOADS_DIR.glob(f"dl_{task_id}_*{ext}"):
                    if candidate.exists():
                        content = candidate.read_text(encoding="utf-8", errors="ignore")
                        # _parse_vtt is actually a bit permissive and works for basic SRT too
                        sub_entries = _parse_vtt(content, 0.0, duration or 99999.0)
                        break
                if sub_entries:
                    break
            
            if sub_entries:
                for seg in suggestions:
                    st = seg["start_seconds"]
                    en = seg["end_seconds"]
                    # Extract text for this segment
                    texts = [e["text"] for e in sub_entries if (e["end"] >= st and e["start"] <= en)]
                    full_text = " ".join(texts).strip()
                    
                    if full_text:
                        # Elite Scoring
                        score_data = _score_viral_moment(full_text, st, en)
                        seg["viral_score"] = score_data["viral_score"]
                        seg["type"] = score_data["type"]
                        seg["reason"] = score_data["reason"]
                        seg["vectors"] = score_data.get("vectors")
                        seg["hook"] = score_data.get("hook_text")
                        seg["subtitle_text"] = full_text
                
                # Sort by Elite Viral Score
                suggestions.sort(key=lambda x: x.get("viral_score", 0), reverse=True)
                # Ensure we return top 10 if available
                suggestions = suggestions[:10]
        except Exception as sub_e:
            print("Error parsing subtitles for elite suggest:", sub_e)

        return response_success(
            data={"suggestions": suggestions, "duration": duration},
            message="Saran segment Elite berhasil dibuat",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat saran: {str(e)}")


# ─── Viral Title Generator ────────────────────────────────────────────────────

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
    if not api_key or genai is None:
        print("GEMINI_API_KEY tidak ditemukan atau library tidak terinstal, menggunakan fallback auto hook.")
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

_VIRAL_DNA: dict[str, tuple[tuple[int, int, int, int], str]] = {
    "rahasia":           ((10, 9, 3, 7), "insight"),
    "secret":            ((10, 9, 3, 7), "insight"),
    "terungkap":         ((9, 10, 5, 8), "insight"),
    "revealed":          ((9, 10, 5, 8), "insight"),
    "ternyata":          ((10, 8, 4, 6), "hook"),
    "you won't believe": ((10, 9, 7, 9), "hook"),
    "wait for it":       ((10, 8, 6, 8), "hook"),
    "plot twist":        ((9, 10, 8, 10), "punchline"),
    "shocking":          ((9, 7, 10, 9), "emotion"),
    "syok":              ((9, 7, 10, 9), "emotion"),
    "kaget":             ((8, 6, 10, 8), "emotion"),
    "OMG":               ((9, 5, 10, 9), "emotion"),
    "rahasia terbesar":  ((10, 10, 6, 9), "insight"),
    "jangan skip":       ((10, 5, 3, 5), "hook"),
    "ini alasannya":     ((9, 8, 4, 6), "insight"),
    "gila":              ((6, 7, 10, 8), "emotion"),
    "parah":             ((6, 7, 10, 8), "emotion"),
    "nangis":            ((4, 5, 10, 9), "emotion"),
    "sedih":             ((3, 4, 9, 7), "emotion"),
    "marah":             ((5, 5, 9, 6), "emotion"),
    "speechless":        ((8, 8, 10, 9), "emotion"),
    "merinding":         ((9, 8, 10, 10), "emotion"),
    "fakta":             ((7, 8, 4, 6), "insight"),
    "tips":              ((8, 8, 3, 7), "insight"),
    "trik":              ((8, 8, 3, 7), "insight"),
    "wajib tau":         ((10, 8, 4, 8), "insight"),
    "must know":         ((10, 8, 4, 8), "insight"),
    "akhirnya":          ((5, 7, 8, 7), "punchline"),
    "turns out":         ((8, 9, 6, 8), "punchline"),
    "bayangkan":         ((9, 8, 7, 7), "hook"),
    "imagine":           ((9, 8, 7, 7), "hook"),
}

_HOOK_STARTERS = [
    "tahukah kamu", "did you know", "bayangkan jika", "imagine if",
    "ini rahasia", "this is the secret", "pernah kepikiran", "ever wondered",
    "berhenti melakukan", "stop doing", "jangan pernah", "never ever",
    "alasan kenapa", "the reason why", "cara tercepat", "fastest way",
    "sebenarnya", "actually", "ada satu hal", "there's one thing"
]

def _score_viral_moment(subtitle_text: str, start_time: float, end_time: float) -> dict:
    """
    Elite Pure-Python Viral Scorer (Zero Dependency).
    Evaluation vectors: Hook, Curiosity, Emotion, Shareability.
    """
    import re as _re

    text = subtitle_text.strip()
    if not text:
        return {"viral_score": 0, "type": "hook", "reason": "No text."}

    text_lower = text.lower()

    # Vector scores (0-10)
    v_hook, v_curiosity, v_emotion, v_shareability = 0, 0, 0, 0
    detected_types = []

    # 1. DNA Keyword Scoring (Vector weights)
    for kw, ((h, c, e, s), t) in _VIRAL_DNA.items():
        if kw in text_lower:
            v_hook = max(v_hook, h)
            v_curiosity = max(v_curiosity, c)
            v_emotion = max(v_emotion, e)
            v_shareability = max(v_shareability, s)
            detected_types.append(t)

    # 2. Curiosity (Question and intrigue markers)
    questions_count = text.count("?")
    intrigue_markers = ["kenapa", "bagaimana", "rahasia", "misteri", "ternyata", "how", "why", "secret"]
    v_curiosity = min(10, v_curiosity + questions_count * 3 + sum(2 for m in intrigue_markers if m in text_lower))

    # 3. Hook Strength (Start of segment)
    # Check for hook starters
    clean_start = text_lower[:100].split('.')[0]
    for starter in _HOOK_STARTERS:
        if clean_start.startswith(starter):
            v_hook = min(10, v_hook + 6)
            detected_types.append("hook")
            break

    # 4. Emotion & Shareability (Intensity markers)
    bangs_count = text.count("!")
    caps_count = len(_re.findall(r"\b[A-Z]{3,}\b", text))
    v_emotion = min(10, v_emotion + round(bangs_count * 0.5) + round(caps_count * 0.5))
    v_shareability = min(10, v_shareability + round(v_hook * 0.3) + round(v_emotion * 0.3))

    # 5. Final Aggregation
    # Weighting: Hook(40%), Curiosity(25%), Emotion(20%), Shareability(15%)
    raw_score = (v_hook * 0.40) + (v_curiosity * 0.25) + (v_emotion * 0.20) + (v_shareability * 0.15)
    total_score = round(raw_score * 10)
    
    # Summary & Reason
    reasons = []
    if v_hook >= 8: reasons.append("Hook pembuka sangat kuat")
    if v_curiosity >= 8: reasons.append("Terdapat elemen penasaran/intrigue")
    if v_emotion >= 8: reasons.append("Muatan emosional/intensitas tinggi")
    if v_shareability >= 8: reasons.append("Konten sangat shareable")
    
    reason = " | ".join(reasons) if reasons else "Segment ini memiliki alur informasi yang baik."
    dom_type = max(set(detected_types), key=detected_types.count) if detected_types else "insight"

    return {
        "viral_score": total_score,
        "type": dom_type,
        "reason": reason,
        "vectors": {"hook": v_hook, "curiosity": v_curiosity, "emotion": v_emotion, "shareability": v_shareability},
        "hook_text": text.split(".")[0][:80] + "..." if len(text.split(".")[0]) > 80 else text.split(".")[0]
    }


class ViralScoreRequest(BaseModel):
    subtitle_text: str
    start_time: float = 0.0
    end_time: float = 0.0


class ViralScoreBatchRequest(BaseModel):
    segments: list[ViralScoreRequest]


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
@router.post("/batch-process/{task_id}")
async def api_youtube_batch_process(task_id: str, req: BatchProcessRequest):
    """
    AI Batch Mode: Automatically detects top N highlights, trims them into clips,
    and extracts subtitles for all of them in one operation.
    """
    task = _recover_task(task_id)
    if not task or task.get("status") != "done":
        # Final attempt: direct path check if task in memory is missing
        candidate = DOWNLOADS_DIR / f"dl_{task_id}_merged.mp4"
        if not candidate.exists():
            candidates = list(DOWNLOADS_DIR.glob(f"dl_{task_id}_*.mp4"))
            if candidates: candidate = candidates[0]
        
        if candidate.exists():
            task = {"status": "done", "file_path": str(candidate)}
        else:
            raise HTTPException(status_code=400, detail=f"Video dengan ID {task_id} tidak ditemukan atau belum selesai didownload.")

    input_path = Path(task["file_path"])
    video_title = task.get("video_title", "Viral Clip").replace(".mp4", "")
    
    # Resilient path check: if the absolute path fails, try relative to current DOWNLOADS_DIR
    if not input_path.exists():
        fallback_path = DOWNLOADS_DIR / input_path.name
        if fallback_path.exists():
            input_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail=f"File media tidak ditemukan di server: {input_path.name}")

    format_type = req.format_type
    samples = req.samples

    try:
        with av.open(str(input_path)) as container:
            duration = float(container.duration / av.time_base) if container.duration else 0.0

        # 1. Get Top Suggestions
        target = 60.0 if format_type == "short" else 600.0
        suggestions = await asyncio.to_thread(
            suggest_segments_from_file,
            input_path=input_path,
            target_seconds=target,
            format_type=format_type,
        )

        # 2. Enrich and Sort by Elite Scoring if Subs exist
        sub_exts = [".vtt", ".srt"]
        sub_content = ""
        sub_entries_raw = []
        for ext in sub_exts:
            for candidate in DOWNLOADS_DIR.glob(f"dl_{task_id}_*{ext}"):
                if candidate.exists():
                    sub_content = candidate.read_text(encoding="utf-8", errors="ignore")
                    sub_entries_raw = _parse_vtt(sub_content, 0.0, duration or 99999.0)
                    break
            if sub_entries_raw:
                break
        
        if sub_entries_raw:
            for seg in suggestions:
                st = seg["start_seconds"]
                en = seg["end_seconds"]
                texts = [e["text"] for e in sub_entries_raw if (e["end"] >= st and e["start"] <= en)]
                full_text = " ".join(texts).strip()
                if full_text:
                    score_data = _score_viral_moment(full_text, st, en)
                    seg["viral_score"] = score_data["viral_score"]
                    seg["type"] = score_data["type"]
                    seg["reason"] = score_data["reason"]
                    seg["subtitle_text"] = full_text
            
            suggestions.sort(key=lambda x: x.get("viral_score", 0), reverse=True)
        
        top_suggestions = suggestions[:samples]
        
        processed_clips = []

        # 3. Batch Trim in semi-parallel (semaphore to avoid CPU melt)
        sem = asyncio.Semaphore(5) # At most 5 parallel trims

        async def _trim_one(seg: dict, idx: int):
            async with sem:
                clip_id = str(uuid.uuid4())
                output_path = CLIPS_DIR / f"{clip_id}.mp4"
                st = seg["start_seconds"]
                en = seg["end_seconds"]
                
                await asyncio.to_thread(
                    pyav_trim,
                    input_path=input_path,
                    output_path=output_path,
                    start_seconds=st,
                    end_seconds=en,
                    format_type=format_type
                )
                
                # Extract specific items for the clip's template
                # Adjust time for subtitle relative to 0
                clip_subs = [
                    {"start": round(e["start"] - st, 2), "end": round(e["end"] - st, 2), "text": e["text"]}
                    for e in sub_entries_raw if (e["start"] >= st and e["end"] <= en)
                ]

                # Generate Auto Title (Hook + Video Title)
                hook_raw = seg.get("subtitle_text", "").strip()
                # Find first sentence or first 45 chars
                hook_title = hook_raw.split(".")[0].split("?")[0].split("!")[0][:50].strip()
                if not hook_title: hook_title = f"Moment #{idx+1}"
                
                # Combine into a viral label: "HOOK! | Original Title"
                # If original title is too long, truncate it
                trunc_video = (video_title[:30] + "...") if len(video_title) > 30 else video_title
                label = f"{hook_title.upper()}! 🔥 | {trunc_video}"

                return {
                    "id": clip_id,
                    "label": label,
                    "start": st,
                    "end": en,
                    "score": seg.get("viral_score", 0),
                    "type": seg.get("type", "insight"),
                    "reason": seg.get("reason", "Momen viral otomatis"),
                    "subtitle_text": seg.get("subtitle_text", ""),
                    "subtitles": clip_subs,
                    "url": f"/api/jobs/clips/{clip_id}.mp4"
                }

        results = await asyncio.gather(*[_trim_one(s, i) for i, s in enumerate(top_suggestions)])
        
        return response_success(
            data={"clips": results, "total": len(results)},
            message=f"{len(results)} viral clips generated automatically!"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch process failed: {str(e)}")
