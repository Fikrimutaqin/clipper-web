import asyncio
import json
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import av
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.responses import FileResponse
from yt_dlp import YoutubeDL

ROOT_DIR = Path(__file__).resolve().parent
STORAGE_DIR = ROOT_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
CLIPS_DIR = STORAGE_DIR / "clips"
DB_PATH = STORAGE_DIR / "app.db"

load_dotenv(dotenv_path=ROOT_DIR / ".env")

@dataclass(frozen=True)
class Settings:
    secret_key: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    @staticmethod
    def from_env() -> "Settings":
        secret_key = os.environ.get("CLIPPER_SECRET_KEY", "")
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        google_redirect_uri = os.environ.get(
            "GOOGLE_REDIRECT_URI", ""
        )
        if not secret_key:
            secret_key = secrets.token_urlsafe(32)
        return Settings(
            secret_key=secret_key,
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            google_redirect_uri=google_redirect_uri,
        )


settings = Settings.from_env()
serializer = URLSafeSerializer(settings.secret_key, salt="clipper-web")

app = FastAPI()
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


def _ensure_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              sid TEXT PRIMARY KEY,
              google_token_json TEXT,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              sid TEXT NOT NULL,
              status TEXT NOT NULL,
              error TEXT,
              source_type TEXT,
              source_url TEXT,
              input_path TEXT NOT NULL,
              output_path TEXT,
              start_seconds REAL NOT NULL,
              end_seconds REAL NOT NULL,
              title TEXT NOT NULL,
              upload_to_youtube INTEGER NOT NULL,
              youtube_video_id TEXT,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        for stmt in (
            "ALTER TABLE jobs ADD COLUMN source_type TEXT",
            "ALTER TABLE jobs ADD COLUMN source_url TEXT",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
async def _startup() -> None:
    _ensure_dirs()
    _init_db()


def _get_or_create_sid(request: Request) -> str:
    sid = request.cookies.get("sid")
    if sid:
        return sid
    return str(uuid.uuid4())


def _set_sid_cookie(response: Any, sid: str) -> Any:
    try:
        response.set_cookie("sid", sid, httponly=True, samesite="lax")
    except Exception:
        pass
    return response


def _upsert_session(sid: str, google_token: Optional[dict[str, Any]]) -> None:
    now = int(time.time())
    conn = _db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (sid, google_token_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sid) DO UPDATE SET
              google_token_json=excluded.google_token_json,
              updated_at=excluded.updated_at
            """,
            (sid, json.dumps(google_token) if google_token else None, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_google_token(sid: str) -> Optional[dict[str, Any]]:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT google_token_json FROM sessions WHERE sid = ?", (sid,)
        ).fetchone()
        if not row:
            return None
        if not row["google_token_json"]:
            return None
        return json.loads(row["google_token_json"])
    finally:
        conn.close()


def _get_google_creds(sid: str) -> Credentials:
    token_data = _get_google_token(sid)
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
            _upsert_session(sid, token_data)
        else:
            raise RuntimeError("Token Google tidak valid, silakan connect ulang")

    return creds


def _download_youtube_to_uploads(*, url: str, job_id: str) -> Path:
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


def _suggest_segments_from_file(
    *,
    input_path: Path,
    target_seconds: float,
    max_candidates: int = 3,
    max_scan_seconds: float = 900.0,
) -> list[dict[str, Any]]:
    dur = float(target_seconds)
    if dur <= 0:
        raise ValueError("target_seconds harus > 0")
    dur = min(dur, 180.0)

    container = av.open(str(input_path))
    try:
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        video_stream = next((s for s in container.streams if s.type == "video"), None)
        if audio_stream is None and video_stream is None:
            raise RuntimeError("Tidak ada stream audio/video yang bisa dianalisis")

        if audio_stream is not None:
            samples: list[tuple[float, float]] = []
            for frame in container.decode(audio_stream):
                t = frame.time
                if t is None:
                    continue
                if t > max_scan_seconds:
                    break
                # Perbaikan error 'av.audio.layout.AudioLayout' untuk versi PyAV baru
                try:
                    arr = frame.to_ndarray()
                except AttributeError:
                    arr = frame.to_ndarray(format="s16")
                
                if arr.ndim == 2:
                    arr = arr.mean(axis=0)
                arr = arr.astype(np.float32, copy=False)
                if arr.size == 0:
                    continue
                rms = float(np.sqrt(np.mean(arr * arr)))
                samples.append((float(t), rms))

            if not samples:
                raise RuntimeError("Gagal membaca audio untuk analisis")

            times = np.array([t for t, _ in samples], dtype=np.float32)
            energies = np.array([e for _, e in samples], dtype=np.float32)

            order = np.argsort(times)
            times = times[order]
            energies = energies[order]

            if energies.size < 5:
                peak_indices = np.array([int(np.argmax(energies))], dtype=np.int32)
            else:
                p = float(np.percentile(energies, 90))
                peak_indices = np.where(energies >= p)[0]
                if peak_indices.size == 0:
                    peak_indices = np.array([int(np.argmax(energies))], dtype=np.int32)

            candidates: list[dict[str, Any]] = []
            for idx in peak_indices.tolist():
                t = float(times[idx])
                start = max(0.0, t - dur * 0.25)
                end = start + dur
                score = float(energies[idx])
                candidates.append({"start_seconds": start, "end_seconds": end, "score": score})

            candidates.sort(key=lambda c: c["score"], reverse=True)
            picked: list[dict[str, Any]] = []
            for c in candidates:
                if len(picked) >= int(max_candidates):
                    break
                ok = True
                for p2 in picked:
                    if abs(float(p2["start_seconds"]) - float(c["start_seconds"])) < dur * 0.5:
                        ok = False
                        break
                if ok:
                    picked.append(c)
            if picked:
                return picked

        if video_stream is not None:
            container.seek(0)
            diffs: list[tuple[float, float]] = []
            prev = None
            frame_step = max(1, int(float(video_stream.average_rate or 30) // 2))
            i = 0
            for frame in container.decode(video_stream):
                t = frame.time
                if t is None:
                    continue
                if t > max_scan_seconds:
                    break
                i += 1
                if i % frame_step != 0:
                    continue
                arr = frame.to_ndarray(format="gray")
                arr = arr[::8, ::8].astype(np.float32, copy=False)
                if prev is not None:
                    diff = float(np.mean(np.abs(arr - prev)))
                    diffs.append((float(t), diff))
                prev = arr

            if not diffs:
                raise RuntimeError("Gagal membaca video untuk analisis")

            times = np.array([t for t, _ in diffs], dtype=np.float32)
            scores = np.array([d for _, d in diffs], dtype=np.float32)
            best = int(np.argmax(scores))
            t = float(times[best])
            start = max(0.0, t - dur * 0.25)
            end = start + dur
            return [{"start_seconds": start, "end_seconds": end, "score": float(scores[best])}]

        raise RuntimeError("Tidak ada stream yang bisa dianalisis")
    finally:
        container.close()


def _create_job(
    sid: str,
    input_path: str,
    start_seconds: float,
    end_seconds: float,
    title: str,
    upload_to_youtube: bool,
    source_type: Optional[str] = None,
    source_url: Optional[str] = None,
    format_type: str = "regular",
) -> str:
    job_id = str(uuid.uuid4())
    now = int(time.time())
    conn = _db()
    try:
        # Tambahkan kolom format_type secara dinamis jika belum ada (SQLite hack sederhana untuk migrasi)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN format_type TEXT DEFAULT 'regular'")
        except Exception:
            pass

        conn.execute(
            """
            INSERT INTO jobs (
              id, sid, status, error, source_type, source_url, input_path, output_path,
              start_seconds, end_seconds, title, upload_to_youtube,
              youtube_video_id, format_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                sid,
                "queued",
                None,
                source_type,
                source_url,
                input_path,
                None,
                float(start_seconds),
                float(end_seconds),
                title,
                1 if upload_to_youtube else 0,
                None,
                format_type,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def _update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    error: Optional[str] = None,
    input_path: Optional[str] = None,
    source_type: Optional[str] = None,
    source_url: Optional[str] = None,
    output_path: Optional[str] = None,
    youtube_video_id: Optional[str] = None,
) -> None:
    updates: list[str] = []
    params: list[Any] = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if error is not None:
        updates.append("error = ?")
        params.append(error)
    if input_path is not None:
        updates.append("input_path = ?")
        params.append(input_path)
    if source_type is not None:
        updates.append("source_type = ?")
        params.append(source_type)
    if source_url is not None:
        updates.append("source_url = ?")
        params.append(source_url)
    if output_path is not None:
        updates.append("output_path = ?")
        params.append(output_path)
    if youtube_video_id is not None:
        updates.append("youtube_video_id = ?")
        params.append(youtube_video_id)
    updates.append("updated_at = ?")
    params.append(int(time.time()))
    params.append(job_id)
    conn = _db()
    try:
        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def _get_job(job_id: str, sid: str) -> Optional[dict[str, Any]]:
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND sid = ?", (job_id, sid)
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def _list_jobs(sid: str, limit: int = 20) -> list[dict[str, Any]]:
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE sid = ? ORDER BY created_at DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _pyav_trim(input_path: Path, output_path: Path, start_seconds: float, end_seconds: float, format_type: str = "regular") -> None:
    if float(end_seconds) <= float(start_seconds):
        raise ValueError("end_seconds harus lebih besar dari start_seconds")

    in_container = av.open(str(input_path))
    try:
        video_stream = next((s for s in in_container.streams if s.type == "video"), None)
        if not video_stream:
            raise RuntimeError("Video stream tidak ditemukan")
        audio_stream = next((s for s in in_container.streams if s.type == "audio"), None)

        out_container = av.open(str(output_path), mode="w")
        try:
            rate = 30
            if video_stream.average_rate is not None:
                try:
                    rate = int(float(video_stream.average_rate))
                except Exception:
                    rate = 30

            out_video = out_container.add_stream("libx264", rate=rate)
            orig_w = int(video_stream.codec_context.width or 1920)
            orig_h = int(video_stream.codec_context.height or 1080)
            
            # Setup Filter Graph agar tidak gepeng (stretch) saat convert ke Shorts
            graph = av.filter.Graph()
            buffer = graph.add_buffer(template=video_stream)
            
            if format_type == "short" and orig_w > orig_h:
                out_video.width = 1080
                out_video.height = 1920
                # Crop bagian tengah sesuai rasio 9:16, lalu scale ke resolusi HD vertikal
                crop = graph.add("crop", "ih*9/16:ih")
                scale = graph.add("scale", "1080:1920")
                buffer.link_to(crop)
                crop.link_to(scale)
                scale.link_to(graph.add("buffersink"))
            else:
                out_video.width = orig_w
                out_video.height = orig_h
                buffer.link_to(graph.add("buffersink"))
                
            graph.configure()
            
            out_video.pix_fmt = "yuv420p"
            out_video.options = {"preset": "medium", "crf": "18"}

            out_audio = None
            if audio_stream is not None:
                out_audio = out_container.add_stream("aac", rate=int(audio_stream.rate or 44100))
                out_audio.bit_rate = 192000
                try:
                    if hasattr(audio_stream, 'layout') and audio_stream.layout is not None:
                        out_audio.layout = getattr(audio_stream.layout, 'name', 'stereo')
                except Exception:
                    out_audio.layout = 'stereo'

            in_container.seek(int(float(start_seconds) * av.time_base))

            done_video = False
            done_audio = audio_stream is None
            streams = [video_stream] + ([audio_stream] if audio_stream is not None else [])

            for packet in in_container.demux(streams):
                for frame in packet.decode():
                    t = frame.time
                    if t is None:
                        continue
                    if t < float(start_seconds):
                        continue
                    if t > float(end_seconds):
                        if packet.stream.type == "video":
                            done_video = True
                        elif packet.stream.type == "audio":
                            done_audio = True
                        continue

                    if packet.stream.type == "video":
                        graph.push(frame)
                        while True:
                            try:
                                filtered_frame = graph.pull()
                                for out_packet in out_video.encode(filtered_frame):
                                    out_container.mux(out_packet)
                            except av.error.EOFError:
                                break
                            except Exception:
                                break
                    elif packet.stream.type == "audio" and out_audio is not None:
                        for out_packet in out_audio.encode(frame):
                            out_container.mux(out_packet)

                if done_video and done_audio:
                    break

            # Flush
            try:
                graph.push(None)
                while True:
                    try:
                        filtered_frame = graph.pull()
                        for out_packet in out_video.encode(filtered_frame):
                            out_container.mux(out_packet)
                    except av.error.EOFError:
                        break
                    except Exception:
                        break
            except Exception:
                pass

            for out_packet in out_video.encode():
                out_container.mux(out_packet)
            if out_audio is not None:
                for out_packet in out_audio.encode():
                    out_container.mux(out_packet)
        finally:
            out_container.close()
    finally:
        in_container.close()


def _youtube_upload(
    *,
    sid: str,
    file_path: Path,
    title: str,
) -> str:
    creds = _get_google_creds(sid)
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(str(file_path), mimetype="video/mp4", resumable=True)
    
    # Menambahkan hashtag Shorts ke title/deskripsi jika belum ada
    # YouTube secara otomatis mendeteksi Shorts jika durasi < 60s dan rasio vertikal/persegi,
    # namun menambahkan hashtag #Shorts membantu algoritmanya.
    final_title = title if "#Shorts" in title else f"{title} #Shorts"
    description = f"Clip dari video trending.\n\n#Shorts #Trending #Clipper"

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
                _youtube_upload, sid=sid, file_path=output_path, title=str(job["title"])
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


def _google_flow(*, state: str, redirect_uri: str) -> Flow:
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


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    sid = _get_or_create_sid(request)
    response = templates.TemplateResponse("index.html", {"request": request})
    return _set_sid_cookie(response, sid)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    sid = _get_or_create_sid(request)
    token = _get_google_token(sid)
    jobs = _list_jobs(sid)
    response = templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "is_connected": bool(token), "jobs": jobs},
    )
    response.set_cookie("sid", sid, httponly=True, samesite="lax")
    return response


@app.get("/auth/google/start")
async def google_start(request: Request) -> RedirectResponse:
    sid = _get_or_create_sid(request)
    state = secrets.token_urlsafe(16)
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
    response.set_cookie(
        "oauth_state", serializer.dumps({"state": state}), httponly=True, samesite="lax"
    )
    return response


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    sid = _get_or_create_sid(request)
    raw_state = request.cookies.get("oauth_state", "")
    try:
        payload = serializer.loads(raw_state) if raw_state else {}
    except BadSignature:
        payload = {}
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


@app.get("/api/me")
async def api_me(request: Request) -> JSONResponse:
    sid = _get_or_create_sid(request)
    token = _get_google_token(sid)
    return _set_sid_cookie(JSONResponse({"sid": sid, "is_connected": bool(token)}), sid)


@app.get("/api/youtube/videos")
async def api_youtube_videos(request: Request, limit: int = 25) -> JSONResponse:
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


def _parse_iso8601_duration(duration: str) -> str:
    if not duration:
        return "0:00"
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not match:
        return "0:00"
    h, m, s = match.groups()
    h = int(h) if h else 0
    m = int(m) if m else 0
    s = int(s) if s else 0
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def _topic_to_query(topic: str) -> str:
    t = (topic or "").strip().lower()
    if t in ("finance", "financing"):
        return "finance investing money"
    if t in ("trading",):
        return "trading forex crypto stocks"
    if t in ("ai", "podcast ai", "ai podcast"):
        return "AI podcast"
    return t or "finance trading AI podcast"


@app.get("/api/youtube/discover")
async def api_youtube_discover(
    request: Request,
    limit: int = 20,
    region: str = "ID",
) -> JSONResponse:
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
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

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

    ydl_opts = {
        "format": "best[ext=mp4]/best",
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
            filepath = ydl.prepare_filename(info)
            DOWNLOAD_TASKS[task_id]['status'] = 'done'
            DOWNLOAD_TASKS[task_id]['file_path'] = str(filepath)
    except Exception as e:
        DOWNLOAD_TASKS[task_id]['status'] = 'error'
        DOWNLOAD_TASKS[task_id]['error'] = str(e)

@app.post("/api/youtube/download")
async def api_youtube_download(request: Request, youtube_url: str = Form(...)) -> JSONResponse:
    sid = _get_or_create_sid(request)
    task_id = str(uuid.uuid4())
    DOWNLOAD_TASKS[task_id] = {"status": "downloading", "progress": 0, "file_path": "", "error": ""}
    asyncio.create_task(asyncio.to_thread(_download_youtube_task, task_id, youtube_url))
    return _set_sid_cookie(JSONResponse({"task_id": task_id}), sid)

@app.get("/api/youtube/download/{task_id}")
async def api_youtube_download_status(request: Request, task_id: str) -> JSONResponse:
    if task_id not in DOWNLOAD_TASKS:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    return JSONResponse(DOWNLOAD_TASKS[task_id])

@app.get("/api/youtube/search")
async def api_youtube_search(
    request: Request,
    q: str = "",
    limit: int = 15,
) -> JSONResponse:
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
    upload_to_youtube: bool = Form(False),
    format_type: str = Form("regular"),
) -> JSONResponse:
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
        upload_to_youtube=bool(upload_to_youtube),
        source_type="youtube" if youtube_url or server_file else "upload",
        source_url=youtube_url or None,
        format_type=format_type,
    )

    asyncio.create_task(_process_job(job_id, sid))
    return _set_sid_cookie(JSONResponse({"job_id": job_id}), sid)


@app.get("/api/jobs/{job_id}")
async def api_get_job(request: Request, job_id: str) -> JSONResponse:
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
