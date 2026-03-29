from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
import asyncio
import uuid
import os
from google_auth import get_google_creds
from googleapiclient.discovery import build
from services.job_service import _download_youtube_task, DOWNLOAD_TASKS
from db import get_db, UserSession
from sqlalchemy.orm import Session
from core import response_success, CLIPS_DIR
from processing import pyav_trim, suggest_segments_from_file
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

router = APIRouter()

class TrimRequest(BaseModel):
    task_id: str
    start_seconds: float
    end_seconds: float
    format_type: str = "regular" # regular or short

@router.get("/discover")
async def api_youtube_discover(
    region: str = "ID", 
    limit: int = 20, 
    request: Request = None,
    db: Session = Depends(get_db)
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

@router.post("/download")
async def api_youtube_download(url: str, request: Request):
    if not url:
        raise HTTPException(status_code=400, detail="URL YouTube harus diisi")
    
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {"status": "downloading", "progress": 0, "url": url}
    
    # Run download in background
    asyncio.create_task(asyncio.to_thread(_download_youtube_task, task_id, url))
    
    return response_success(data={"task_id": task_id}, message="Download dimulai")

@router.get("/download/{task_id}")
async def api_youtube_download_status(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return response_success(data=task)

@router.post("/trim")
async def api_youtube_trim(req: TrimRequest):
    task = DOWNLOAD_TASKS.get(req.task_id)
    if not task or task.get("status") != "done":
        raise HTTPException(status_code=400, detail="Video belum selesai didownload atau tidak ditemukan")
    
    input_path = Path(task["file_path"])
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
        
        return response_success(
            data={
                "clip_id": clip_id,
                "url": f"/api/jobs/clips/{clip_id}.mp4" # Assuming a static/media endpoint exists
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
    try:
        # Get metadata for duration check
        with av.open(str(input_path)) as container:
            duration = float(container.duration / av.time_base)
            
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
