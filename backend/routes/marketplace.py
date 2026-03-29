from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from _database.db import get_db, User, Job, Portfolio
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
    else:
        job.status = "IN_PROGRESS" # Kembali ke Clipper untuk revisi
        job.owner_notes = review.notes
        
    job.updated_at = int(time.time())
    db.commit()
    return response_success(message="Review berhasil disimpan")

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
    db.commit()
    return response_success(message="Berhasil mengambil pekerjaan", data={"job_id": job_id})

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
    db.commit()
    return response_success(message="Dana berhasil dititipkan di Escrow (ClipFIX)")

# --- Clipper Portfolios ---

@router.get("/clippers")
async def list_clippers(db: Session = Depends(get_db)):
    clippers = db.query(User).filter(User.role == "CLIPPER").all()
    result = []
    for c in clippers:
        portfolio = db.query(Portfolio).filter(Portfolio.user_id == c.id).first()
        result.append({
            "id": c.id,
            "full_name": c.full_name,
            "avatar_url": c.avatar_url,
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
