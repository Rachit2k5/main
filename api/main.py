from dotenv import load_dotenv
import os
import uuid
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
from enum import Enum
from typing import Optional, List
from datetime import datetime
from collections import defaultdict
from jose import jwt, JWTError
from fastapi import Cookie
from fastapi.responses import RedirectResponse

# --- CONFIG & INIT ---
load_dotenv()
app = FastAPI(title="Smart Civic Issue Reporting System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "../static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- JWT CONFIG ---
JWT_SECRET = os.environ.get("JWT_SECRET", "your-very-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600 * 24 * 7  # 7 days token validity

# --- MODELS ---
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
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    user_avatar: Optional[str] = None

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

def analyze_photo_ai(file_path: str) -> str:
    # Placeholder for AI integration
    return "AI: Detected potential infrastructure issue—please verify."

def allowed_file(filename, allowed_exts):
    return '.' in filename and filename.split(".")[-1].lower() in allowed_exts

# --- ROUTES ---

@app.post("/issues", response_model=Issue)
async def report_issue(
    category: IssueCategory = Form(...),
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    photo: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    access_token: Optional[str] = Cookie(None)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    user_name = payload.get("name")
    user_email = payload.get("email")
    user_avatar = payload.get("picture")

    if not (user_name and user_email and user_avatar):
        raise HTTPException(status_code=401, detail="Incomplete user information")

    issue_id = str(uuid.uuid4())
    now = datetime.utcnow()
    photo_filename = audio_filename = video_filename = ai_analysis = None

    if photo:
        if not allowed_file(photo.filename, {"jpg", "jpeg", "png", "gif", "bmp"}):
            raise HTTPException(status_code=400, detail="Photo must be an image file")
        file_ext = photo.filename.split('.')[-1]
        photo_filename = f"{issue_id}_photo.{file_ext}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        try:
            with open(photo_path, "wb") as f:
                f.write(await photo.read())
            ai_analysis = analyze_photo_ai(photo_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Photo upload failed: {str(e)}")

    if audio:
        if not allowed_file(audio.filename, {"mp3", "wav", "ogg", "webm"}):
            raise HTTPException(status_code=400, detail="Audio must be a valid audio file")
        file_ext = audio.filename.split('.')[-1]
        audio_filename = f"{issue_id}_audio.{file_ext}"
        audio_path = os.path.join(UPLOAD_DIR, audio_filename)
        try:
            with open(audio_path, "wb") as f:
                f.write(await audio.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Audio upload failed: {str(e)}")

    if video:
        if not allowed_file(video.filename, {"mp4", "webm", "mov", "avi", "mkv"}):
            raise HTTPException(status_code=400, detail="Video must be a valid video file")
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
        updated_at=now,
        user_name=user_name,
        user_email=user_email,
        user_avatar=user_avatar
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
    by_status = defaultdict(int)
    response_times = []
    for issue in issues_db.values():
        by_category[issue.category] = by_category.get(issue.category, 0) + 1
        by_status[issue.status] += 1
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

# --- GOOGLE OAUTH ROUTES ---
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REDIRECT_URI = os.environ["GOOGLE_REDIRECT_URI"]

@app.get("/auth/google/login")
async def google_login():
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        "&scope=openid%20email%20profile"
        "&access_type=offline"
        "&prompt=select_account"
    )
    return {"auth_url": url}

@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None):
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")
    access_token = token_resp.json().get("access_token")
    userinfo_resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if userinfo_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="User info fetch failed")
    return userinfo_resp.json()

@app.get("/auth/google/me")
async def get_google_user(access_token: Optional[str] = Cookie(None)):
    if not access_token:
        return JSONResponse(status_code=401, content={"detail": "No access token cookie"})
    try:
        payload = jwt.decode(access_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return JSONResponse(status_code=401, content={"detail": "Invalid token"})
    return {
        "email": payload.get("email"),
        "name": payload.get("name"),
        "picture": payload.get("picture"),
    }

@app.get("/auth/google/logout")
async def google_logout():
    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie("access_token")
    return response

@app.get("/")
async def serve_frontend():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse(content={"message": "Smart Civic Issue Reporting API is running."})
