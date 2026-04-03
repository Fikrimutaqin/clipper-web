from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from _database.db import get_db, User, Job, Portfolio, Notification
from routes.auth import get_current_user
from core import response_success
from pydantic import BaseModel
from typing import List, Optional
import uuid
import time
import json

router = APIRouter()

class JobCreate(BaseModel):
    title: str
    description: str
    budget: float
    source_url: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    budget: float
    status: str
    owner_id: str
    clipper_id: Optional[str] = None
    result_url: Optional[str] = None
    owner_notes: Optional[str] = None
    created_at: int

class PortfolioUpdate(BaseModel):
    bio: str
    social_links: dict
    video_samples: List[str]

class JobSubmission(BaseModel):
    result_url: str

class JobReview(BaseModel):
    approve: bool
    notes: Optional[str] = None

class JobInvite(BaseModel):
    clipper_id: str

class JobRating(BaseModel):
    rating: int
    review: Optional[str] = None

def _create_notification(db: Session, *, user_id: str, type: str, message: str, meta: Optional[dict] = None) -> None:
    now = int(time.time())
    notif = Notification(
        user_id=user_id,
        type=type,
        message=message,
        meta_json=json.dumps(meta or {}),
        created_at=now,
        read_at=None,
    )
    db.add(notif)

# --- Marketplace Jobs ---

@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    db: Session = Depends(get_db)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan")
    return response_success(data=job)

@router.post("/jobs/{job_id}/submit")
async def submit_job_result(
    job_id: str,
    submission: JobSubmission,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa men-submit hasil")
    
    job = db.query(Job).filter(Job.id == job_id, Job.clipper_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan atau bukan milik Anda")
    
    job.result_url = submission.result_url
    job.status = "REVIEW"
    job.updated_at = int(time.time())
    if job.owner_id:
        _create_notification(
            db,
            user_id=job.owner_id,
            type="JOB_SUBMITTED",
            message=f"Hasil pekerjaan '{job.title}' sudah di-submit oleh clipper.",
            meta={"job_id": job.id},
        )
    db.commit()
    return response_success(message="Berhasil men-submit hasil pekerjaan")

@router.post("/jobs/{job_id}/review")
async def review_job_result(
    job_id: str,
    review: JobReview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Hanya Owner yang bisa mereview pekerjaan")
    
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan")
    
    if review.approve:
        job.status = "COMPLETED"
        # Release payment automatically on approval
        if job.payment_status == "ESCROW_HOLD":
            job.payment_status = "RELEASED"
        if job.clipper_id:
            _create_notification(
                db,
                user_id=job.clipper_id,
                type="JOB_APPROVED",
                message=f"Pekerjaan '{job.title}' disetujui. Pembayaran diproses.",
                meta={"job_id": job.id},
            )
    else:
        job.status = "IN_PROGRESS" # Kembali ke Clipper untuk revisi
        job.owner_notes = review.notes
        if job.clipper_id:
            _create_notification(
                db,
                user_id=job.clipper_id,
                type="JOB_REVISION",
                message=f"Pekerjaan '{job.title}' butuh revisi: {review.notes or '-'}",
                meta={"job_id": job.id},
            )
        
    job.updated_at = int(time.time())
    db.commit()
    return response_success(message="Review berhasil disimpan")

@router.post("/jobs/{job_id}/rate")
async def rate_job(
    job_id: str,
    rating_in: JobRating,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Hanya Owner yang bisa memberi rating")

    if rating_in.rating < 1 or rating_in.rating > 5:
        raise HTTPException(status_code=400, detail="Rating harus 1 sampai 5")

    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan")

    if job.status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Rating hanya bisa diberikan setelah pekerjaan COMPLETED")

    if not job.clipper_id:
        raise HTTPException(status_code=400, detail="Job belum memiliki clipper")

    if job.owner_rating is not None:
        raise HTTPException(status_code=400, detail="Rating sudah pernah diberikan")

    job.owner_rating = rating_in.rating
    job.owner_review = rating_in.review
    job.updated_at = int(time.time())
    _create_notification(
        db,
        user_id=job.clipper_id,
        type="RATED",
        message=f"Kamu mendapat rating {rating_in.rating}/5 untuk pekerjaan '{job.title}'.",
        meta={"job_id": job.id, "rating": rating_in.rating},
    )
    db.commit()
    return response_success(message="Rating berhasil disimpan")

@router.post("/jobs")
async def create_marketplace_job(
    job_in: JobCreate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Hanya Business Owner yang bisa memposting lowongan")
    
    job_id = str(uuid.uuid4())
    now = int(time.time())
    new_job = Job(
        id=job_id,
        owner_id=current_user.id,
        title=job_in.title,
        description=job_in.description,
        budget=job_in.budget,
        source_url=job_in.source_url,
        status="OPEN",
        created_at=now,
        updated_at=now
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return response_success(data=new_job, message="Pekerjaan berhasil diposting")

@router.get("/jobs")
async def list_open_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).filter(Job.status == "OPEN").all()
    return response_success(data=jobs)

@router.post("/jobs/{job_id}/apply")
async def apply_for_job(
    job_id: str, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang bisa mengambil pekerjaan")
    
    job = db.query(Job).filter(Job.id == job_id, Job.status == "OPEN").first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan atau sudah diambil")
    
    job.clipper_id = current_user.id
    job.status = "IN_PROGRESS"
    job.updated_at = int(time.time())
    if job.owner_id:
        _create_notification(
            db,
            user_id=job.owner_id,
            type="JOB_TAKEN",
            message=f"Pekerjaan '{job.title}' sudah diambil oleh clipper.",
            meta={"job_id": job.id, "clipper_id": current_user.id},
        )
    db.commit()
    return response_success(message="Berhasil mengambil pekerjaan", data={"job_id": job_id})

@router.post("/jobs/{job_id}/invite")
async def invite_clipper_to_job(
    job_id: str,
    invite: JobInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Hanya Owner yang bisa mengundang Clipper")

    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan")

    if job.status != "OPEN":
        raise HTTPException(status_code=400, detail="Pekerjaan tidak dalam status OPEN")

    if job.payment_status != "ESCROW_HOLD":
        raise HTTPException(status_code=400, detail="Dana belum dititipkan di Escrow. Silakan deposit terlebih dahulu.")

    clipper = db.query(User).filter(User.id == invite.clipper_id, User.role == "CLIPPER").first()
    if not clipper:
        raise HTTPException(status_code=404, detail="Clipper tidak ditemukan")

    job.clipper_id = invite.clipper_id
    job.status = "IN_PROGRESS"
    job.updated_at = int(time.time())

    _create_notification(
        db,
        user_id=invite.clipper_id,
        type="JOB_INVITED",
        message=f"Kamu diundang untuk mengerjakan '{job.title}'.",
        meta={"job_id": job.id, "owner_id": current_user.id},
    )
    _create_notification(
        db,
        user_id=current_user.id,
        type="JOB_INVITE_SENT",
        message=f"Undangan pekerjaan '{job.title}' terkirim ke {clipper.full_name}.",
        meta={"job_id": job.id, "clipper_id": invite.clipper_id},
    )
    db.commit()

    return response_success(
        message="Clipper berhasil diundang dan pekerjaan dimulai",
        data={"job_id": job_id, "clipper_id": invite.clipper_id, "status": job.status}
    )

@router.post("/jobs/{job_id}/pay")
async def pay_to_escrow(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "OWNER":
        raise HTTPException(status_code=403, detail="Hanya Owner yang bisa membayar ke Escrow")
    
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Pekerjaan tidak ditemukan")
    
    if job.payment_status != "PENDING":
        raise HTTPException(status_code=400, detail="Pembayaran sudah diproses atau sedang ditahan")
    
    job.payment_status = "ESCROW_HOLD"
    job.updated_at = int(time.time())
    _create_notification(
        db,
        user_id=current_user.id,
        type="ESCROW_DEPOSITED",
        message=f"Dana escrow untuk '{job.title}' berhasil dititipkan.",
        meta={"job_id": job.id},
    )
    if job.clipper_id:
        _create_notification(
            db,
            user_id=job.clipper_id,
            type="ESCROW_AVAILABLE",
            message=f"Dana escrow untuk '{job.title}' sudah tersedia. Kamu bisa mulai bekerja.",
            meta={"job_id": job.id},
        )
    db.commit()
    return response_success(message="Dana berhasil dititipkan di Escrow (ClipFIX)")

# --- Notifications ---

@router.get("/notifications")
async def list_my_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .count()
    )
    result = []
    for n in notifs:
        result.append(
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "meta": json.loads(n.meta_json) if n.meta_json else {},
                "created_at": n.created_at,
                "read_at": n.read_at,
            }
        )
    return response_success(data=result, meta={"unread_count": unread_count})

@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    notif.read_at = int(time.time())
    db.commit()
    return response_success(message="Notifikasi ditandai sudah dibaca")

@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = int(time.time())
    (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .update({Notification.read_at: now})
    )
    db.commit()
    return response_success(message="Semua notifikasi ditandai sudah dibaca")

# --- Clipper Portfolios ---

@router.get("/clippers")
async def list_clippers(db: Session = Depends(get_db)):
    clippers = db.query(User).filter(User.role == "CLIPPER").all()
    rating_rows = (
        db.query(
            Job.clipper_id,
            func.avg(Job.owner_rating),
            func.count(Job.owner_rating),
        )
        .filter(Job.owner_rating.isnot(None))
        .group_by(Job.clipper_id)
        .all()
    )
    ratings = {}
    for clipper_id, avg_rating, count_rating in rating_rows:
        ratings[clipper_id] = {
            "avg": float(avg_rating) if avg_rating is not None else None,
            "count": int(count_rating) if count_rating is not None else 0,
        }
    result = []
    for c in clippers:
        portfolio = db.query(Portfolio).filter(Portfolio.user_id == c.id).first()
        r = ratings.get(c.id, {"avg": None, "count": 0})
        result.append({
            "id": c.id,
            "full_name": c.full_name,
            "avatar_url": c.avatar_url,
            "rating_avg": r["avg"],
            "rating_count": r["count"],
            "portfolio": {
                "bio": portfolio.bio if portfolio else "",
                "social_links": json.loads(portfolio.social_links) if portfolio and portfolio.social_links else {},
                "video_samples": json.loads(portfolio.video_samples) if portfolio and portfolio.video_samples else []
            }
        })
    return response_success(data=result)

@router.post("/portfolio")
async def update_my_portfolio(
    p_in: PortfolioUpdate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role != "CLIPPER":
        raise HTTPException(status_code=403, detail="Hanya Clipper yang memiliki portfolio")
    
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).first()
    if portfolio:
        portfolio.bio = p_in.bio
        portfolio.social_links = json.dumps(p_in.social_links)
        portfolio.video_samples = json.dumps(p_in.video_samples)
    else:
        portfolio = Portfolio(
            user_id=current_user.id,
            bio=p_in.bio,
            social_links=json.dumps(p_in.social_links),
            video_samples=json.dumps(p_in.video_samples)
        )
        db.add(portfolio)
    
    db.commit()
    return response_success(message="Portfolio berhasil diperbarui")
