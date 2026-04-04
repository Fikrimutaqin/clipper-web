import os
import uuid
import time
import json
import asyncio
from typing import Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from _database.db import get_db, Job, init_db
from core import UPLOADS_DIR, response_success, settings
from routes.auth import get_current_user
from processing import render_video_with_template
from pathlib import Path

router = APIRouter()

@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a local video file for processing."""
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in [".mp4", ".mov", ".avi", ".mkv"]:
        raise HTTPException(status_code=400, detail="Format file tidak didukung. Gunakan MP4, MOV, AVI, atau MKV.")

    job_id = str(uuid.uuid4())
    file_name = f"upload_{job_id}{file_ext}"
    file_path = UPLOADS_DIR / file_name

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan file: {str(e)}")

    # Create Job record
    now = int(time.time())
    new_job = Job(
        id=job_id,
        owner_id=current_user.id,
        title=file.filename,
        source_type="upload",
        input_path=str(file_path),
        status="UPLOADED",
        created_at=now,
        updated_at=now
    )
    db.add(new_job)
    db.commit()

    return response_success(
        data={"video_id": job_id, "file_name": file_name},
        message="Video berhasil diupload."
    )

@router.post("/select-media/{media_type}/{media_id}")
async def select_from_media_library(
    media_type: str, # 'download' or 'clip'
    media_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Select an existing video from the Media Library (either a full download or a clip)."""
    from core import DOWNLOADS_DIR, CLIPS_DIR
    
    file_path = None
    title = f"Media {media_id}"

    if media_type == "download":
        # Search for dl_{media_id}_*.mp4
        matches = list(DOWNLOADS_DIR.glob(f"dl_{media_id}_*.mp4"))
        if matches:
            file_path = matches[0]
    elif media_type == "clip":
        # Search for {media_id}.mp4 in clips
        candidate = CLIPS_DIR / f"{media_id}.mp4"
        if candidate.exists():
            file_path = candidate
            title = f"Clip {media_id}"

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File media tidak ditemukan di server.")

    job_id = str(uuid.uuid4())
    now = int(time.time())
    new_job = Job(
        id=job_id,
        owner_id=current_user.id,
        title=title,
        source_type="media_library",
        input_path=str(file_path),
        status="UPLOADED",
        created_at=now,
        updated_at=now
    )
    db.add(new_job)
    db.commit()

    return response_success(
        data={
            "video_id": job_id,
            "filename": file_path.name
        },
        message="Media berhasil dipilih dari library."
    )

@router.post("/process/{video_id}/subtitle")
async def generate_subtitle_local(
    video_id: str,
    target_lang: str = "id",
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate subtitles locally using Faster-Whisper (No API Cost)."""
    job = db.query(Job).filter(Job.id == video_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Video tidak ditemukan")

    input_path = Path(job.input_path)
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="File video fisik tidak ditemukan")

    try:
        from faster_whisper import WhisperModel
        
        # Load model 'base' is lightweight (approx 150MB) and fast on CPU
        model_size = "base"
        # Run on CPU. If you have GPU, use device="cuda"
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        print(f"Transcribing {input_path} locally...")
        segments, info = model.transcribe(str(input_path), beam_size=5)
        
        entries = []
        for s in segments:
            entries.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text.strip()
            })

        return response_success(
            data={"subtitles": entries, "language": info.language},
            message=f"Subtitle berhasil di-generate secara lokal (AI Whisper {info.language})!"
        )

    except Exception as e:
        print(f"WHISPER ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Gagal memproses subtitle lokal: {str(e)}")

@router.post("/process/{video_id}/render")
async def render_final_video(
    video_id: str,
    req_body: dict, # includes subtitle entries and styling
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """Burn edited subtitles into the video."""
    job = db.query(Job).filter(Job.id == video_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Video tidak ditemukan")

    from core import CLIPS_DIR
    output_filename = f"final_{job.id}.mp4"
    output_path = CLIPS_DIR / output_filename
    
    # template_config based on processing.py's expectations
    req_template = req_body.get("template", {})
    template_config = {
        "fontname": req_template.get("fontname", "Montserrat"),
        "fontsize": int(req_template.get("fontsize", 80)),
        "primary_colour": req_template.get("primary_colour", "FFFFFF"),
        "outline_colour": req_template.get("outline_colour", "000000"),
        "outline": int(req_template.get("outline", 5)),
        "alignment": int(req_template.get("alignment", 2)),
        "margin_v": int(req_template.get("margin_v", 200)),
        "uppercase": req_template.get("uppercase", True),
        "entries": req_body.get("entries", req_template.get("entries", []))
    }

    try:
        await asyncio.to_thread(
            render_video_with_template,
            input_video=job.input_path,
            output_video=str(output_path),
            template_config=template_config
        )
        
        # Update job
        job.output_path = str(output_path)
        job.status = "COMPLETED"
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        clip_url = f"/api/jobs/clips/{output_filename}"
        
        return response_success(
            data={
                "video_url": f"{base_url}{clip_url}",
                "job_id": job.id,
                "filename": output_filename
            },
            message="Video berhasil di-render."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal render video: {str(e)}")

@router.post("/process/{video_id}/content-ai")
async def generate_content_ai(
    video_id: str,
    req_body: dict, # includes subtitles
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate catchy Title and Description based on subtitle context using AI."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY needed for content generation.")

    subtitles = req_body.get("subtitles", [])
    if not subtitles:
        raise HTTPException(status_code=400, detail="Subtitles are required to generate content context.")

    full_text = " ".join([s.get("text", "") for s in subtitles])
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        prompt = f"""
        Berdasarkan transkrip subtitle video berikut:
        "{full_text}"
        
        Buatkan 1 Judul yang sangat viral (catchy) dan 1 Deskripsi singkat yang menarik untuk social media (TikTok/Reels/Shorts).
        
        Format output HANYA JSON:
        {{
          "title": "Judul Viral...",
          "description": "Deskripsi Menarik..."
        }}
        """
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```json"): text = text[len("```json"):].strip()
        if text.endswith("```"): text = text[:-3].strip()
        
        data = json.loads(text)
        return response_success(data=data, message="Content AI berhasil dibuat.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal generate content: {str(e)}")
