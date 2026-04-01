from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from core import ensure_dirs, CLIPS_DIR
from _database.db import init_db
from routes import auth, jobs, marketplace, youtube
import os

app = FastAPI(title="ClipFIX API", version="0.1.0")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    ensure_dirs()
    init_db()

@app.get("/")
async def root():
    return {"message": "Welcome to ClipFIX API", "status": "online"}

# Serve static files for clips
app.mount("/api/jobs/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")

# Include Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(marketplace.router, prefix="/api/marketplace", tags=["marketplace"])
