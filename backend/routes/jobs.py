from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from _database.db import get_db, User, Job
from routes.auth import get_current_user
from core import response_success
from typing import List

router = APIRouter()

@router.get("/my-jobs")
async def get_my_jobs(
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if current_user.role == "OWNER":
        # Owner melihat job yang dia posting
        jobs = db.query(Job).filter(Job.owner_id == current_user.id).order_by(Job.created_at.desc()).all()
    elif current_user.role == "CLIPPER":
        # Clipper melihat job yang dia ambil
        jobs = db.query(Job).filter(Job.clipper_id == current_user.id).order_by(Job.created_at.desc()).all()
    else:
        jobs = []
    
    return response_success(
        message="Data jobs berhasil diambil",
        data=jobs
    )
