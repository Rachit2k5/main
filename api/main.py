from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from enum import Enum
from datetime import datetime
from typing import Optional, List
import os
import uuid
from collections import defaultdict

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(title="Smart Civic Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Upload directory path in Vercel env (use /tmp for temp storage)
UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    # Placeholder AI
    return "AI: Detected potential issue; please verify"

def allowed_file(filename: str, allowed_exts: set) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_exts

@app.post("/api/issues", response_model=Issue)
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
    saved_avatar_url = None
    if avatar_file:
        ext = avatar_file.filename.rsplit('.', 1)[1].lower()
        if ext not in {"jpg", "jpeg", "png", "gif", "bmp"}:
            raise HTTPException(status_code=400, detail="Invalid avatar file type")
        avatar_filename = f"avatar_{uuid.uuid4()}.{ext}"
        avatar_path = os.path.join(UPLOAD_DIR, avatar_filename)
        with open(avatar_path, "wb") as f:
            f.write(await avatar_file.read())
        saved_avatar_url = f"/uploads/{avatar_filename}"
    elif user_avatar:
        saved_avatar_url = user_avatar

    photo_filename = None
    ai_analysis = None
    if photo:
        if not allowed_file(photo.filename, {"jpg", "jpeg", "png", "gif", "bmp"}):
            raise HTTPException(status_code=400, detail="Invalid photo file type")
        photo_filename = f"photo_{uuid.uuid4()}.{photo.filename.rsplit('.',1)[1].lower()}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        with open(photo_path, "wb") as f:
            f.write(await photo.read())
        ai_analysis = analyze_photo_ai(photo_path)

    audio_filename = None
    if audio:
        if not allowed_file(audio.filename, {"mp3", "wav", "ogg", "webm"}):
            raise HTTPException(status_code=400, detail="Invalid audio file type")
        audio_filename = f"audio_{uuid.uuid4()}.{audio.filename.rsplit('.',1)[1].lower()}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(await audio.read())

    video_filename = None
    if video:
        if not allowed_file(video.filename, {"mp4", "webm", "mov", "avi", "mkv"}):
            raise HTTPException(status_code=400, detail="Invalid video file type")
        video_filename = f"video_{uuid.uuid4()}.{video.filename.rsplit('.',1)[1].lower()}"
        video_path = os.path.join(UPLOAD_DIR, video_filename)
        with open(video_path, "wb") as f:
            f.write(await video.read())

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

@app.get("/api/issues", response_model=List[Issue])
async def list_issues(status: Optional[IssueStatus] = None, category: Optional[IssueCategory] = None):
    results = list(issues_db.values())
    if status:
        results = [issue for issue in results if issue.status == status]
    if category:
        results = [issue for issue in results if issue.category == category]
    return results

@app.patch("/api/issues/{issue_id}/status", response_model=Issue)
async def update_status(issue_id: str, status: IssueStatus):
    if issue_id not in issues_db:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue = issues_db[issue_id]
    issue.status = status
    issue.updated_at = datetime.utcnow()
    return issue

@app.get("/api/analytics/summary")
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
    return {"message": "Smart Civic Reporting API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
