import os
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from enum import Enum
from typing import Optional, List
from datetime import datetime

app = FastAPI(title="Smart Civic Issue Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# Ensure /tmp exists for uploads
UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static files only if the directory exists
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ========== MODELS ==========

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

    @validator("latitude")
    def latitude_valid(cls, v):
        if v < -90 or v > 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @validator("longitude")
    def longitude_valid(cls, v):
        if v < -180 or v > 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v

# ========== IN-MEMORY "DATABASE" ==========
issues_db = {}

# ========== AI ANALYSIS ==========
def analyze_photo_ai(file_path: str) -> str:
    # Placeholder for a real AI model—replace with your own or a cloud API call.
    return "AI: Detected potential infrastructure issue—please verify."

# ========== ROUTES ==========

@app.post("/issues", response_model=Issue)
async def report_issue(
    category: IssueCategory = Form(...),
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None)
):
    # Validate coordinates
    if not (-90 <= latitude <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")

    issue_id = str(uuid.uuid4())
    now = datetime.utcnow()
    photo_filename = audio_filename = video_filename = ai_analysis = None

    # --- PHOTO ---
    if photo:
        file_ext = photo.filename.split('.')[-1]
        photo_filename = f"{issue_id}_photo.{file_ext}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        try:
            with open(photo_path, "wb") as f:
                f.write(await photo.read())
            ai_analysis = analyze_photo_ai(photo_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Photo upload failed: {str(e)}")
    # --- AUDIO ---
    if audio:
        file_ext = audio.filename.split('.')[-1]
        audio_filename = f"{issue_id}_audio.{file_ext}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        try:
            with open(audio_path, "wb") as f:
                f.write(await audio.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Audio upload failed: {str(e)}")
    # --- VIDEO ---
    if video:
        file_ext = video.filename.split('.')[-1]
        video_filename = f"{issue_id}_video.{file_ext}"
        video_path = os.path.join(UPLOAD_DIR, video_filename)
        try:
            with open(video_path, "wb") as f:
                f.write(await video.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Video upload failed: {str(e)}")

    issue_obj = Issue(
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
        updated_at=now
    )

    issues_db[issue_id] = issue_obj
    return issue_obj

@app.get("/issues", response_model=List[Issue])
async def list_issues(
    status: Optional[IssueStatus] = Query(None),
    category: Optional[IssueCategory] = Query(None)
):
    results = list(issues_db.values())
    if status:
        results = [i for i in results if i.status == status]
    if category:
        results = [i for i in results if i.category == category]
    return results

@app.patch("/issues/{issue_id}/status", response_model=Issue)
async def update_status(issue_id: str, status_update: IssueStatus):
    issue = issues_db.get(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = status_update
    issue.updated_at = datetime.utcnow()
    issues_db[issue_id] = issue
    return issue

@app.get("/analytics/summary")
async def analytics_summary():
    total_issues = len(issues_db)
    by_category = {}
    by_status = {}
    response_times = []
    for issue in issues_db.values():
        by_category[issue.category] = by_category.get(issue.category, 0) + 1
        by_status[issue.status] = by_status.get(issue.status, 0) + 1
        if issue.status == IssueStatus.resolved:
            delta = (issue.updated_at - issue.created_at).total_seconds()
            if delta > 0:
                response_times.append(delta)
    avg_response_time = sum(response_times) / len(response_times) if response_times else None
    return {
        "total_issues": total_issues,
        "issues_by_category": by_category,
        "issues_by_status": by_status,
        "average_resolution_time_seconds": avg_response_time,
    }

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse(content={"message": "Smart Civic Issue Reporting API is running."})
