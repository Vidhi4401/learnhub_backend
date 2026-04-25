from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, Base
import models
import os

# ── Import all routers ──
from routers import (auth, organization, dashboard, courses, topics, videos,
                     assignments, quizzes, profile, student, chatbot,
                     admin_router, materials, meetings, notifications,
                     video_summarizer, superadmin_router)

app = FastAPI(title="LearningHub API")

# ── CORS — allow your Vercel frontend + localhost for dev ──
ALLOWED_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
]

# Add Vercel URL from environment variable (set this in Render dashboard after first deploy)
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
if FRONTEND_URL:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Create upload folders (used as temp storage only — real files go to Cloudinary) ──
os.makedirs("uploads", exist_ok=True)

# ── Create DB tables ──
Base.metadata.create_all(bind=engine)

# ── Serve uploaded files (temp/local fallback) ──
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Register all routers ──
app.include_router(auth.router)
app.include_router(organization.router)
app.include_router(dashboard.router)
app.include_router(courses.router)
app.include_router(topics.router)
app.include_router(videos.router)
app.include_router(assignments.router)
app.include_router(quizzes.router)
app.include_router(profile.router)
app.include_router(student.router)
app.include_router(chatbot.router)
app.include_router(admin_router.router)
app.include_router(materials.router)
app.include_router(meetings.router)
app.include_router(notifications.router)
app.include_router(video_summarizer.router)
app.include_router(superadmin_router.router)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "LearningHub API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)