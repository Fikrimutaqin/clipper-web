import asyncio
import os
import shutil
import uuid
import re
import av
from pathlib import Path
from typing import Any, Optional
from yt_dlp import YoutubeDL
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from core import UPLOADS_DIR, DOWNLOADS_DIR, CLIPS_DIR
from _database.db import update_job, get_job, get_google_token
from google_auth import get_google_creds
from processing import pyav_trim

DOWNLOAD_TASKS: dict[str, dict[str, Any]] = {}

def _download_youtube_task(task_id: str, url: str):
    """Background download task that writes progress into DOWNLOAD_TASKS."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    if task_id in DOWNLOAD_TASKS:
        DOWNLOAD_TASKS[task_id]["status"] = "downloading"

    def progress_hook(d):
        if d['status'] == 'downloading':
            p_str = d.get('_percent_str', '0%')
            p_str = ansi_escape.sub('', p_str).replace('%', '').strip()
            try:
                DOWNLOAD_TASKS[task_id]['progress'] = float(p_str)
            except Exception:
                pass
        elif d['status'] == 'finished':
            DOWNLOAD_TASKS[task_id]['progress'] = 100
            if DOWNLOAD_TASKS.get(task_id, {}).get("status") == "downloading":
                DOWNLOAD_TASKS[task_id]["status"] = "merging"

    url = (url or "").strip().strip("`").strip().strip('"').strip("'")
    ydl_opts = {
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
    }
    use_browser_cookies = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip() in {"1", "true", "yes"}
    if use_browser_cookies:
        ydl_opts["cookiesfrombrowser"] = ("chrome",)

    try:
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            msg = str(e)
            if "could not find chrome cookies database" in msg.lower() and "cookiesfrombrowser" in ydl_opts:
                ydl_opts.pop("cookiesfrombrowser", None)
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
            else:
                raise

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
                DOWNLOAD_TASKS[task_id]["status"] = "merging"
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

def _youtube_upload(*, sid: str, file_path: Path, title: str, description: str = "", format_type: str = "regular") -> str:
    def build_metadata(raw_title: str, raw_description: str, fmt: str) -> tuple[str, str]:
        base_title = (raw_title or "").strip() or "Clipper Video"
        if len(base_title) > 100:
            base_title = base_title[:100]
        desc = (raw_description or "").strip() or "Generated by Clipper.\n\n#Clipper"
        if len(desc) > 5000:
            desc = desc[:5000]
        return base_title, desc

    creds = get_google_creds(sid)
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(str(file_path), mimetype="video/mp4", resumable=True)
    final_title, final_desc = build_metadata(title, description, format_type)

    response = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": final_title, "description": final_desc},
            "status": {"privacyStatus": "public"},
        },
        media_body=media,
    ).execute()
    return str(response.get("id"))

async def process_job_task(job_id: str, sid: str):
    job = get_job(job_id, sid)
    if not job: return
    try:
        update_job(job_id, status="processing", error=None)
        input_path = Path(str(job.get("input_path") or ""))
        if not input_path.exists(): raise RuntimeError("File input tidak ditemukan")
        
        output_path = CLIPS_DIR / f"{job_id}.mp4"
        pyav_trim(
            input_path=input_path,
            output_path=output_path,
            start_seconds=float(job["start_seconds"]),
            end_seconds=float(job["end_seconds"]),
            format_type=str(job.get("format_type", "regular"))
        )
        update_job(job_id, status="clipped", output_path=str(output_path))

        if job.get("upload_to_youtube"):
            update_job(job_id, status="uploading")
            vid_id = await asyncio.to_thread(
                _youtube_upload, sid=sid, file_path=output_path,
                title=str(job["title"]), description=str(job.get("description") or "")
            )
            update_job(job_id, status="done", youtube_video_id=vid_id)
        else:
            update_job(job_id, status="done")
    except Exception as e:
        update_job(job_id, status="error", error=str(e))
