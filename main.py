from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from database import engine, Base
import models
import os

from routers import (auth, organization, dashboard, courses, topics, videos,
                     assignments, quizzes, profile, student, chatbot,
                     admin_router, materials, meetings, notifications,
                     video_summarizer, superadmin_router)

app = FastAPI(title="LearningHub API")

# ── CORS ──
ALLOWED_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://learnhub-frontend-one.vercel.app",
]

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str):
    origin = request.headers.get("origin", "")
    response = JSONResponse(content={}, status_code=200)
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Max-Age"] = "3600"
    return response

os.makedirs("uploads", exist_ok=True)
Base.metadata.create_all(bind=engine)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
