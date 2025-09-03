import os
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from enum import Enum
from typing import Optional, List
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Enum as SqlEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ========== SETUP ==========
app = FastAPI(title="Smart Civic Issue Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

DATABASE_URL = "sqlite:///./civic_issues.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

UPLOAD_DIR = "/tmp"  # Use /tmp for all file ops on Vercel/serverless

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

class IssueDB(Base):
    __tablename__ = "issues"
    id = Column(String, primary_key=True)
    category = Column(SqlEnum(IssueCategory), nullable=False)
    description = Column(String, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    photo_filename = Column(String, nullable=True)
    audio_filename = Column(String, nullable=True)
    video_filename = Column(String, nullable=True)
    ai_analysis = Column(String, nullable=True)
    status = Column(SqlEnum(IssueStatus), default=IssueStatus.reported)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

Base.metadata.create_all(bind=engine)

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

# ========== AI ANALYSIS ==========
def analyze_photo_ai(file_path: str) -> str:
    # Placeholder for a real AI model—replace with your own or a cloud API call.
    # For demo: returns a random analysis string.
    # EXAMPLE: return my_ai_predict_function(file_path)
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

    db = Session()
    issue_id = str(uuid.uuid4())
    now = datetime.utcnow()
    photo_filename = audio_filename = video_filename = ai_analysis = None

    # --- PHOTO ---
    if photo:
        file_ext = photo.filename.split('.')[-1]
        photo_filename = f"{issue_id}_photo.{file_ext}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        with open(photo_path, "wb") as f:
            f.write(await photo.read())
        ai_analysis = analyze_photo_ai(photo_path)

    # --- AUDIO ---
    if audio:
        file_ext = audio.filename.split('.')[-1]
        audio_filename = f"{issue_id}_audio.{file_ext}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(await audio.read())

    # --- VIDEO ---
    if video:
        file_ext = video.filename.split('.')[-1]
        video_filename = f"{issue_id}_video.{file_ext}"
        video_path = os.path.join(UPLOAD_DIR, video_filename)
        with open(video_path, "wb") as f:
            f.write(await video.read())

    issue_obj = IssueDB(
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
    db.add(issue_obj)
    db.commit()
    db.refresh(issue_obj)
    db.close()

    return Issue(**issue_obj.__dict__)

@app.get("/issues", response_model=List[Issue])
async def list_issues(
    status: Optional[IssueStatus] = Query(None),
    category: Optional[IssueCategory] = Query(None)
):
    db = Session()
    query = db.query(IssueDB)
    if status:
        query = query.filter(IssueDB.status == status)
    if category:
        query = query.filter(IssueDB.category == category)
    issues = query.all()
    db.close()
    return [Issue(**i.__dict__) for i in issues]

@app.patch("/issues/{issue_id}/status", response_model=Issue)
async def update_status(issue_id: str, status_update: IssueStatus):
    db = Session()
    issue = db.query(IssueDB).filter(IssueDB.id == issue_id).first()
    if not issue:
        db.close()
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = status_update
    issue.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(issue)
    db.close()
    return Issue(**issue.__dict__)

@app.get("/analytics/summary")
async def analytics_summary():
    db = Session()
    total_issues = db.query(IssueDB).count()
    by_category = {cat.value: db.query(IssueDB).filter(IssueDB.category == cat).count() for cat in IssueCategory}
    by_status = {status.value: db.query(IssueDB).filter(IssueDB.status == status).count() for status in IssueStatus}
    resolved_issues = db.query(IssueDB).filter(IssueDB.status == IssueStatus.resolved).all()
    response_times = [
        (i.updated_at - i.created_at).total_seconds()
        for i in resolved_issues if (i.updated_at - i.created_at).total_seconds() > 0
    ]
    avg_response_time = sum(response_times) / len(response_times) if response_times else None
    db.close()
    return {
        "total_issues": total_issues,
        "issues_by_category": by_category,
        "issues_by_status": by_status,
        "average_resolution_time_seconds": avg_response_time,
    }

@app.get("/")
async def root():
    return JSONResponse({"msg": "Smart Civic Issue Reporting API running."})

