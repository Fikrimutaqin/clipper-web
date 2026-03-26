import json
import sqlite3
import time
from typing import Any, Optional

from core import DB_PATH


def db() -> sqlite3.Connection:
    """Open a SQLite connection with Row mapping enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create database tables and apply lightweight migrations."""
    conn = db()
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
              description TEXT,
              upload_to_youtube INTEGER NOT NULL,
              youtube_video_id TEXT,
              format_type TEXT DEFAULT 'regular',
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            )
            """
        )
        for stmt in (
            "ALTER TABLE jobs ADD COLUMN source_type TEXT",
            "ALTER TABLE jobs ADD COLUMN source_url TEXT",
            "ALTER TABLE jobs ADD COLUMN description TEXT",
            "ALTER TABLE jobs ADD COLUMN format_type TEXT DEFAULT 'regular'",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def upsert_session(sid: str, google_token: Optional[dict[str, Any]]) -> None:
    """Insert or update the current Google token JSON for a session."""
    now = int(time.time())
    conn = db()
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


def get_google_token(sid: str) -> Optional[dict[str, Any]]:
    """Fetch the stored Google token JSON for a given session id."""
    conn = db()
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


def create_job(
    *,
    sid: str,
    input_path: str,
    start_seconds: float,
    end_seconds: float,
    title: str,
    description: str = "",
    upload_to_youtube: bool,
    source_type: Optional[str] = None,
    source_url: Optional[str] = None,
    format_type: str = "regular",
) -> str:
    """Create a new clipping job record and return its id."""
    import uuid

    job_id = str(uuid.uuid4())
    now = int(time.time())
    conn = db()
    try:
        conn.execute(
            """
            INSERT INTO jobs (
              id, sid, status, error, source_type, source_url, input_path, output_path,
              start_seconds, end_seconds, title, description, upload_to_youtube,
              youtube_video_id, format_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                description,
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


def update_job(
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
    """Update a job row with any provided fields."""
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
    conn = db()
    try:
        conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()


def get_job(job_id: str, sid: str) -> Optional[dict[str, Any]]:
    """Return a job by id for the given session, or None if not found."""
    conn = db()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND sid = ?", (job_id, sid)
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def list_jobs(sid: str, limit: int = 20) -> list[dict[str, Any]]:
    """List recent jobs for a session id (newest first)."""
    conn = db()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE sid = ? ORDER BY created_at DESC LIMIT ?",
            (sid, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
