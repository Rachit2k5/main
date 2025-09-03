import os
import uuid
from fastapi import FastAPI, HTTPException, Query, File, UploadFile, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, validator
from enum import Enum
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="Smart Civic Issue Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Serve frontend files responsively (make sure your frontend is mobile responsive)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


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
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
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


issues_db = {}

department_map = {
    IssueCategory.pothole: "Roadworks",
    IssueCategory.streetlight: "Utilities",
    IssueCategory.garbage: "Sanitation",
    IssueCategory.water: "Waterworks",
    IssueCategory.others: "General"
}


# Example: Load AI model once (placeholder)
# from some_ai_module import load_model, analyze_image
# model = load_model()

def analyze_photo_ai(file_path: str) -> str:
    # Replace this placeholder with real AI model inference code
    # Example:
    # result = analyze_image(model, file_path)
    # return result

    # Currently returns a mock message:
    return "AI analysis: Image indicates possible infrastructure damage."


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
    # Validate coordinates explicitly here as well for extra safety
    if latitude < -90 or latitude > 90:
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if longitude < -180 or longitude > 180:
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")

    issue_id = str(uuid.uuid4())
    now = datetime.utcnow()

    photo_url = None
    audio_url = None
    video_url = None
    ai_analysis = None

    # Save photo and analyze it if uploaded
    if photo:
        ext = photo.filename.split('.')[-1]
        photo_filename = f"{issue_id}_photo.{ext}"
        photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
        with open(photo_path, "wb") as f:
            f.write(await photo.read())
        photo_url = f"/{UPLOAD_FOLDER}/{photo_filename}"

        # Call AI bot to analyze photo (replace with real AI inference)
        ai_analysis = analyze_photo_ai(photo_path)

    # Save audio if uploaded
    if audio:
        ext = audio.filename.split('.')[-1]
        audio_filename = f"{issue_id}_audio.{ext}"
        audio_path = os.path.join(UPLOAD_FOLDER, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(await audio.read())
        audio_url = f"/{UPLOAD_FOLDER}/{audio_filename}"

    # Save video if uploaded
    if video:
        ext = video.filename.split('.')[-1]
        video_filename = f"{issue_id}_video.{ext}"
        video_path = os.path.join(UPLOAD_FOLDER, video_filename)
        with open(video_path, "wb") as f:
            f.write(await video.read())
        video_url = f"/{UPLOAD_FOLDER}/{video_filename}"

    new_issue = Issue(
        id=issue_id,
        category=category,
        description=description,
        latitude=latitude,
        longitude=longitude,
        photo_url=photo_url,
        audio_url=audio_url,
        video_url=video_url,
        ai_analysis=ai_analysis,
        status=IssueStatus.reported,
        created_at=now,
        updated_at=now,
    )

    issues_db[issue_id] = new_issue
    return new_issue

@app.get("/issues", response_model=List[Issue])
async def list_issues(
    status: Optional[IssueStatus] = Query(None),
    category: Optional[IssueCategory] = Query(None),
    department: Optional[str] = Query(None)
):
    results = list(issues_db.values())
    if status:
        results = [i for i in results if i.status == status]
    if category:
        results = [i for i in results if i.category == category]
    if department:
        filtered_cats = [cat for cat, dept in department_map.items() if dept.lower() == department.lower()]
        results = [i for i in results if i.category in filtered_cats]
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

    avg_response_time = sum(response_times)/len(response_times) if response_times else None
    return {
        "total_issues": total_issues,
        "issues_by_category": by_category,
        "issues_by_status": by_status,
        "average_resolution_time_seconds": avg_response_time,
        "departments": department_map
    }

@app.get("/departments")
async def list_departments():
    return list(set(department_map.values()))

@app.get("/")
async def root():
    # Serve your frontend's index.html file here
    return FileResponse("frontend/index.html")

# Note on deployment for mobile/live access:
# 1. Deploy this FastAPI app to a public cloud platform (e.g., AWS, Heroku, Google Cloud).
# 2. Use a domain with HTTPS for security and browser trust.
# 3. Ensure mobile-responsive frontend served under /static.
# 4. Mobile users then access a single public URL to use the app live on any browser/device.
# 5. Optionally, wrap frontend in a PWA or webview native app shell for installable experience.
