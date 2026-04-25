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
import shutil

router = APIRouter(prefix="/api/v1/videos", tags=["Video Summarizer"])

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

def get_ffmpeg_location():
    """
    Returns ffmpeg path that works on both Windows (local dev) and Linux (Render).
    On Render, ffmpeg is pre-installed and available in PATH.
    """
    # 1. Check for Windows .exe (local dev)
    win_paths = [
        os.path.join(BACKEND_DIR, "ffmpeg.exe"),
        os.path.join(BACKEND_DIR, "bin", "ffmpeg.exe"),
    ]
    for p in win_paths:
        if os.path.exists(p):
            return os.path.dirname(p)  # return directory, not file

    # 2. Check Linux/Mac system ffmpeg (Render has this pre-installed)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return os.path.dirname(system_ffmpeg)

    # 3. Not found — yt-dlp will try on its own
    return None


def download_audio(video_url: str):
    """Downloads audio from a video URL using yt-dlp, works on Windows and Linux."""
    temp_dir = tempfile.gettempdir()
    timestamp = int(time.time())
    file_prefix = f"ai_sum_{timestamp}_%(id)s"

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

    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        ydl_opts['ffmpeg_location'] = ffmpeg_location

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        audio_path = os.path.join(temp_dir, f"ai_sum_{timestamp}_{info['id']}.mp3")

        if not os.path.exists(audio_path):
            for f in os.listdir(temp_dir):
                if info['id'] in f and f.endswith(".mp3") and str(timestamp) in f:
                    audio_path = os.path.join(temp_dir, f)
                    break

        return audio_path