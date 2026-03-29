import json
import time
import os
from typing import Any, Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, Boolean, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "mysql+pymysql://user:password@db:3306/clipper")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="OWNER") # OWNER, CLIPPER, ADMIN
    full_name = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    jobs_posted = relationship("Job", back_populates="owner", foreign_keys="Job.owner_id")
    jobs_assigned = relationship("Job", back_populates="clipper", foreign_keys="Job.clipper_id")
    portfolio = relationship("Portfolio", back_populates="user", uselist=False)

class UserSession(Base):
    __tablename__ = "sessions"
    sid = Column(String(255), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    google_token_json = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String(36), primary_key=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    clipper_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    status = Column(String(50), default="OPEN") # OPEN, IN_PROGRESS, REVIEW, COMPLETED, ERROR
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    budget = Column(Float, default=0.0)
    
    # Video details
    source_type = Column(String(50)) # youtube, upload
    source_url = Column(Text, nullable=True)
    input_path = Column(String(255), nullable=True)
    output_path = Column(String(255), nullable=True)
    start_seconds = Column(Float, nullable=True)
    end_seconds = Column(Float, nullable=True)
    format_type = Column(String(20), default="regular")
    
    # YouTube Integration
    upload_to_youtube = Column(Boolean, default=False)
    youtube_video_id = Column(String(100), nullable=True)
    
    # Marketplace Result
    result_url = Column(Text, nullable=True) # Link to finished video or cloud storage
    owner_notes = Column(Text, nullable=True) # Feedback from owner
    payment_status = Column(String(50), default="PENDING") # PENDING, ESCROW_HOLD, RELEASED, REFUNDED
    
    error = Column(Text, nullable=True)
    created_at = Column(Integer, nullable=False)
    updated_at = Column(Integer, nullable=False)
    
    owner = relationship("User", back_populates="jobs_posted", foreign_keys=[owner_id])
    clipper = relationship("User", back_populates="jobs_assigned", foreign_keys=[clipper_id])

class Portfolio(Base):
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True)
    bio = Column(Text, nullable=True)
    social_links = Column(Text, nullable=True) # Store as JSON string
    video_samples = Column(Text, nullable=True) # Store as JSON string
    
    user = relationship("User", back_populates="portfolio")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper functions for Google Session
def upsert_session(sid: str, google_token: Optional[dict[str, Any]], user_id: Optional[str] = None):
    db = SessionLocal()
    now = int(time.time())
    try:
        session = db.query(UserSession).filter(UserSession.sid == sid).first()
        if session:
            session.google_token_json = json.dumps(google_token) if google_token else None
            session.updated_at = now
            if user_id:
                session.user_id = user_id
        else:
            session = UserSession(
                sid=sid,
                user_id=user_id,
                google_token_json=json.dumps(google_token) if google_token else None,
                created_at=now,
                updated_at=now
            )
            db.add(session)
        db.commit()
    finally:
        db.close()

def get_google_token(sid: str) -> Optional[dict[str, Any]]:
    db = SessionLocal()
    try:
        session = db.query(UserSession).filter(UserSession.sid == sid).first()
        if session and session.google_token_json:
            return json.loads(session.google_token_json)
        return None
    finally:
        db.close()

def create_job(**kwargs) -> str:
    import uuid
    db = SessionLocal()
    job_id = str(uuid.uuid4())
    now = int(time.time())
    try:
        job = Job(
            id=job_id,
            created_at=now,
            updated_at=now,
            **kwargs
        )
        db.add(job)
        db.commit()
        return job_id
    finally:
        db.close()

def update_job(job_id: str, **kwargs):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)
            job.updated_at = int(time.time())
            db.commit()
    finally:
        db.close()

def get_job(job_id: str, sid: str) -> Optional[dict[str, Any]]:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id, Job.sid == sid).first()
        if job:
            return {c.name: getattr(job, c.name) for c in job.__table__.columns}
        return None
    finally:
        db.close()

def list_jobs(sid: str, limit: int = 20) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.sid == sid).order_by(Job.created_at.desc()).limit(limit).all()
        return [{c.name: getattr(job, c.name) for c in job.__table__.columns} for job in jobs]
    finally:
        db.close()
