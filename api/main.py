from dotenv import load_dotenv
import os
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from enum import Enum
from typing import Optional, List
from datetime import datetime
from collections import defaultdict


load_dotenv()

app = FastAPI(title="Smart Civic Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Expose uploaded files via /uploads URL
UPLOAD_URL_PATH = "/uploads"
app.mount(UPLOAD_URL_PATH, StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Static frontend directory, adjust if needed
STATIC_DIR = os.path.join(os.path.dirname(__file__), "../static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class IssueCategory(str, Enum):
    pothole = "pothole"
    streetlight = "streetlight"
    garbage = "garbage"
    water = "water"
    others = "others"

class IssueStatus(str, Enum):
    reported = "reported"
    acknowledged = "acknowledged"
    in_progress = "in_progress"
    resolved = "resolved"

class Issue(BaseModel):
    id: str
    category: IssueCategory
    description: str
    latitude: float
    longitude: float
    photo_filename: Optional[str] = None
    audio_filename: Optional[str] = None
    video_filename: Optional[str] = None
    ai_analysis: Optional[str] = None
    status: IssueStatus = IssueStatus.reported
    created_at: datetime
    updated_at: datetime
    user_name: str
    user_email: str
    user_avatar: Optional[str] = None

    @validator("latitude")
    def latitude_valid(cls, v):
        if not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @validator("longitude")
    def longitude_valid(cls, v):
        if not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180 and 180")
        return v


issues_db = {}

def analyze_photo_ai(file_path: str) -> str:
    # Placeholder for AI analysis
    return "AI: Detected potential issue; please verify"

def allowed_file(filename: str, allowed_exts: set) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_exts


@app.post("/issues", response_model=Issue)
async def report_issue(
    category: IssueCategory = Form(...),
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    user_name: str = Form(...),
    user_email: str = Form(...),
    user_avatar: Optional[str] = Form(None),
    avatar_file: Optional[UploadFile] = File(None),
    photo: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
):

    # Handle avatar: prefer file upload
    saved_avatar_url = None
    if avatar_file:
        ext = avatar_file.filename.rsplit('.', 1)[1].lower()
        if ext not in {"jpg", "jpeg", "png", "gif", "bmp"}:
            raise HTTPException(status_code=400, detail="Avatar file must be a valid image")
        avatar_filename = f"avatar_{uuid.uuid4()}.{ext}"
        avatar_path = os.path.join(UPLOAD_DIR, avatar_filename)
        try:
            with open(avatar_path, "wb") as f:
                f.write(await avatar_file.read())
            saved_avatar_url = f"{UPLOAD_URL_PATH}/{avatar_filename}"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")
    elif user_avatar:
        saved_avatar_url = user_avatar


    # Handle photo
    photo_filename = None
    ai_analysis = None
    if photo:
        if not allowed_file(photo.filename, {"jpg", "jpeg", "png", "gif", "bmp"}):
            raise HTTPException(status_code=400, detail="Photo must be a valid image file")
        photo_filename = f"photo_{uuid.uuid4()}.{photo.filename.rsplit('.',1)[1].lower()}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        try:
            with open(photo_path, "wb") as f:
                f.write(await photo.read())
            ai_analysis = analyze_photo_ai(photo_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Photo upload failed: {str(e)}")

    # Handle audio
    audio_filename = None
    if audio:
        if not allowed_file(audio.filename, {"mp3", "wav", "ogg", "webm"}):
            raise HTTPException(status_code=400, detail="Audio must be a valid audio file")
        audio_filename = f"audio_{uuid.uuid4()}.{audio.filename.rsplit('.',1)[1].lower()}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        try:
            with open(audio_path, "wb") as f:
                f.write(await audio.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Audio upload failed: {str(e)}")

    # Handle video
    video_filename = None
    if video:
        if not allowed_file(video.filename, {"mp4", "webm", "mov", "avi", "mkv"}):
            raise HTTPException(status_code=400, detail="Video must be a valid video file")
        video_filename = f"video_{uuid.uuid4()}.{video.filename.rsplit('.',1)[1].lower()}"
        video_path = os.path.join(UPLOAD_DIR, video_filename)
        try:
            with open(video_path, "wb") as f:
                f.write(await video.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Video upload failed: {str(e)}")

    issue_id = str(uuid.uuid4())
    now = datetime.utcnow()

    issue = Issue(
        id=issue_id,
        category=category,
        description=description,
        latitude=latitude,
        longitude=longitude,
        photo_filename=photo_filename,
        audio_filename=audio_filename,
        video_filename=video_filename,
        ai_analysis=ai_analysis,
        status=IssueStatus.reported,
        created_at=now,
        updated_at=now,
        user_name=user_name,
        user_email=user_email,
        user_avatar=saved_avatar_url,
    )

    issues_db[issue_id] = issue
    return issue


@app.get("/issues", response_model=List[Issue])
async def list_issues(
    status: Optional[IssueStatus] = None,
    category: Optional[IssueCategory] = None,
):
    results = list(issues_db.values())
    if status is not None:
        results = [issue for issue in results if issue.status == status]
    if category is not None:
        results = [issue for issue in results if issue.category == category]
    return results


@app.patch("/issues/{issue_id}/status", response_model=Issue)
async def update_status(issue_id: str, status: IssueStatus):
    if issue_id not in issues_db:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue = issues_db[issue_id]
    issue.status = status
    issue.updated_at = datetime.utcnow()
    return issue


@app.get("/analytics/summary")
async def analytics_summary():
    total_issues = len(issues_db)
    by_category = defaultdict(int)
    by_status = defaultdict(int)
    resolution_times = []

    for issue in issues_db.values():
        by_category[issue.category] += 1
        by_status[issue.status] += 1
        if issue.status == IssueStatus.resolved:
            delta = (issue.updated_at - issue.created_at).total_seconds()
            if delta > 0:
                resolution_times.append(delta)

    avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else None

    return {
        "total_issues": total_issues,
        "issues_by_category": dict(by_category),
        "issues_by_status": dict(by_status),
        "average_resolution_time_seconds": avg_resolution,
    }


@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "Smart Civic Reporting API is running"})
