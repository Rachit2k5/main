from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from enum import Enum
import uuid
import os
from typing import Optional, List
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For demo, use your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use /tmp/uploads directory for saving photos
BASE_UPLOAD_DIR = "/tmp"
UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

class IssueCategory(str, Enum):
    Pothole = "Pothole"
    Street_Light = "Street Light"
    Water_Supply = "Water Supply"
    Garbage = "Garbage"
    Traffic_Signal = "Traffic Signal"
    Other = "Other"

class IssueStatus(str, Enum):
    Submitted = "Submitted"
    In_Progress = "In Progress"
    Resolved = "Resolved"
    Rejected = "Rejected"

class IssuePriority(str, Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Emergency = "Emergency"

class Issue(BaseModel):
    id: str
    title: str
    category: IssueCategory
    priority: IssuePriority
    location: str
    description: str
    photo_filename: Optional[str] = None
    status: IssueStatus = IssueStatus.Submitted
    created_at: datetime
    updated_at: datetime

issues_db = {}

@app.post("/api/report", response_model=Issue)
async def report_issue(
    issue_title: str = Form(...),
    issue_category: IssueCategory = Form(...),
    issue_priority: IssuePriority = Form(...),
    issue_location: str = Form(...),
    issue_description: str = Form(...),
    issue_photo: Optional[UploadFile] = File(None),
):
    photo_filename = None
    if issue_photo:
        ext = issue_photo.filename.rsplit('.', 1)[-1]
        filename = f"photo_{uuid.uuid4()}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)   # Save to /tmp/uploads
        with open(filepath, "wb") as f:
            f.write(await issue_photo.read())
        photo_filename = filename  # Store file name only

    now = datetime.utcnow()
    issue_id = str(uuid.uuid4())
    issue = Issue(
        id=issue_id,
        title=issue_title,
        category=issue_category,
        priority=issue_priority,
        location=issue_location,
        description=issue_description,
        photo_filename=photo_filename,
        status=IssueStatus.Submitted,
        created_at=now,
        updated_at=now,
    )
    issues_db[issue_id] = issue
    return issue

@app.get("/api/reports", response_model=List[Issue])
async def get_reports(status: Optional[IssueStatus] = None, category: Optional[IssueCategory] = None):
    results = list(issues_db.values())
    if status:
        results = [i for i in results if i.status == status]
    if category:
        results = [i for i in results if i.category == category]
    return results

@app.patch("/api/admin/reports/{issue_id}/status", response_model=Issue)
async def update_status(issue_id: str, status: IssueStatus):
    issue = issues_db.get(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = status
    issue.updated_at = datetime.utcnow()
    return issue

# Serve uploaded images stored in /tmp/uploads folder
@app.get("/api/uploads/{filename}")
async def get_uploaded_image(filename: str):
    filepath = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return StreamingResponse(open(filepath, "rb"), media_type="image/jpeg")
    else:
        raise HTTPException(status_code=404, detail="Image not found")

@app.get("/api/health")
def health():
    return {"status": "ok"}
