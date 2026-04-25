from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas, shutil, os, re, requests
from dependencies import get_current_teacher
from typing import Optional

router = APIRouter(tags=["Videos"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def fetch_youtube_duration(url: str) -> int:
    """Helper to extract duration in minutes from YouTube HTML."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        # Regex to find duration in milliseconds or ISO8601
        match = re.search(r'"approxDurationMs":"(\d+)"', response.text)
        if match:
            ms = int(match.group(1))
            return max(1, round(ms / 1000 / 60))
    except Exception as e:
        print(f"[Video Duration Fetch Error] {e}")
    return 10 # Fallback

@router.get("/api/v1/teacher/get-video-duration")
def get_video_duration(url: str, teacher: models.User = Depends(get_current_teacher)):
    if "youtube.com" in url or "youtu.be" in url:
        duration = fetch_youtube_duration(url)
        return {"duration": duration}
    return {"duration": 10}


from cloudinary_utils import upload_to_cloudinary

@router.post("/api/v1/teacher/topics/{topic_id}/videos")
def create_video(
    topic_id: int,
    video_url: Optional[str] = Form(None),
    video_file: Optional[UploadFile] = File(None),
    duration: int = Form(10),
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    final_url = video_url

    if video_file and video_file.filename:
        # Use Cloudinary instead of local
        cloud_url = upload_to_cloudinary(video_file, folder="learnhub/videos", resource_type="video")
        if cloud_url:
            final_url = cloud_url

    if not final_url:
        raise HTTPException(status_code=400, detail="Provide either a video URL or a video file.")

    video = models.Video(
        topic_id=topic_id,
        video_url=final_url,
        duration=duration
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return {"video_id": video.id, "video_url": final_url}


@router.get("/api/v1/topics/{topic_id}/videos")
def get_videos(topic_id: int, db: Session = Depends(get_db)):
    return db.query(models.Video).filter(
        models.Video.topic_id == topic_id
    ).all()


@router.put("/api/v1/teacher/videos/{video_id}")
def update_video(
    video_id: int,
    data: schemas.VideoUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    video.video_url = data.video_url
    video.duration  = data.duration
    db.commit()
    return {"message": "Video updated"}


@router.delete("/api/v1/teacher/videos/{video_id}")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    db.delete(video)
    db.commit()
    return {"message": "Video deleted"}
