from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import os
import yt_dlp
import google.generativeai as genai
from config import GOOGLE_API_KEY
from dependencies import get_current_user, get_db
import tempfile
import time

router = APIRouter(prefix="/api/v1/videos", tags=["Video Summarizer"])

# Get backend directory to locate ffmpeg
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

def download_audio(video_url: str):
    """Downloads audio from a video URL using yt-dlp and returns the path to the temp file."""
    temp_dir = tempfile.gettempdir()
    
    # FIX: Use a single timestamp for the entire process to ensure filename consistency
    timestamp = int(time.time())
    file_prefix = f"ai_sum_{timestamp}_%(id)s"
    
    # Check if ffmpeg exists in BACKEND_DIR; if not, let yt-dlp find it in PATH
    ffmpeg_path = os.path.join(BACKEND_DIR, "ffmpeg.exe")
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(temp_dir, f"{file_prefix}.%(ext)s"),
        'quiet': True,
        'no_warnings': True,
    }

    if os.path.exists(ffmpeg_path):
        ydl_opts['ffmpeg_location'] = BACKEND_DIR
    elif os.path.exists(os.path.join(BACKEND_DIR, "bin", "ffmpeg.exe")):
        ydl_opts['ffmpeg_location'] = os.path.join(BACKEND_DIR, "bin")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        # Find the actual filename (it will have the .mp3 extension now)
        audio_path = os.path.join(temp_dir, f"ai_sum_{timestamp}_{info['id']}.mp3")
        
        # Verify it exists, if not, try searching for it
        if not os.path.exists(audio_path):
            for f in os.listdir(temp_dir):
                if info['id'] in f and f.endswith(".mp3") and str(timestamp) in f:
                    audio_path = os.path.join(temp_dir, f)
                    break
                    
        return audio_path

@router.post("/{video_id}/summarize")
def summarize_video(video_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Summarizes a video using Gemini 1.5 Flash without needing transcripts."""
    
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video_url = video.video_url
    audio_file_path = None
    is_temp_file = False

    try:
        # 1. Get the audio/video file
        if video_url.startswith("uploads/"):
            # Local file - Resolve relative to BACKEND_DIR to be safe
            audio_file_path = os.path.abspath(os.path.join(BACKEND_DIR, video_url))
            if not os.path.exists(audio_file_path):
                # Fallback: check relative to current working directory
                audio_file_path = os.path.abspath(os.path.join(os.getcwd(), video_url))
                
            if not os.path.exists(audio_file_path):
                raise HTTPException(status_code=404, detail=f"Local video file not found at: {audio_file_path}")
        elif "youtube.com" in video_url or "youtu.be" in video_url:
            # YouTube URL - must download audio
            audio_file_path = download_audio(video_url)
            is_temp_file = True
        else:
            # External URL (Cloudinary, etc.) - download for reliable upload to Gemini
            audio_file_path = download_audio(video_url)
            is_temp_file = True

        # 2. Upload to Gemini File API
        print(f"[Summarizer] Uploading {audio_file_path} to Gemini...")
        video_file = genai.upload_file(path=audio_file_path)

        # 3. Generate Summary
        print(f"[Summarizer] Generating content...")
        
        # Try a list of models in order of stability/availability
        models_to_try = ["gemini-1.5-flash", "gemini-flash-latest", "gemini-1.5-flash-8b"]
        summary = None
        last_err = None

        for model_name in models_to_try:
            try:
                print(f"[Summarizer] Attempting with model: {model_name}")
                model = genai.GenerativeModel(model_name)
                prompt = """
                Analyze this video and provide a comprehensive, well-formatted summary for a student.
                Use the following Markdown structure:
                
                ### 📌 Key Overview
                A brief 2-3 sentence summary of the entire video.
                
                ### 🎯 Learning Objectives
                List the main goals or things the student will learn.
                
                ### 📝 Detailed Key Points
                *   **Point 1:** Clear explanation.
                *   **Point 2:** Clear explanation.
                (Add more as needed)
                
                ### 💡 Important Takeaways
                A few final sentences highlighting the most critical information to remember.
                
                Keep the tone educational, encouraging, and clear.
                """
                response = model.generate_content([prompt, video_file])
                summary = response.text
                if summary:
                    break
            except Exception as e:
                print(f"[Summarizer] Model {model_name} failed: {str(e)}")
                last_err = e
                continue
        
        if not summary:
            raise last_err or Exception("All models failed to generate a summary.")

        return {"summary": summary}

    except Exception as e:
        print(f"[Summarizer] Error: {str(e)}")
        # Diagnostics: Print available models to help the user identify the correct name
        try:
            print("[Summarizer] Diagnostic: Listing available models...")
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    print(f" - {m.name}")
        except:
            print("[Summarizer] Could not list models.")

        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup local temp file only if it was downloaded
        if is_temp_file and audio_file_path and os.path.exists(audio_file_path):
            try:
                # Small delay to ensure Windows releases the file handle
                time.sleep(1)
                os.remove(audio_file_path)
                print(f"[Summarizer] Cleaned up: {audio_file_path}")
            except Exception as e:
                print(f"[Summarizer] Cleanup warning (non-fatal): {str(e)}")
