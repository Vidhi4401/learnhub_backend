import json
import os
import requests as http_requests
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import SessionLocal
import models, schemas, joblib, pandas as pd, numpy as np
from auth import hash_password, verify_password
from dependencies import get_current_user
from routers.notifications import create_notification
from config import GROQ_API_KEY
from passlib.context import CryptContext

# =========================
# ML MODEL LOADING (load once at startup)
# =========================
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEVEL_MODEL_PATH = os.path.join(base_dir, "ml", "final_level_model.pkl")
RISK_MODEL_PATH  = os.path.join(base_dir, "ml", "final_risk_model.pkl")
SCALER_PATH      = os.path.join(base_dir, "ml", "final_scaler.pkl")

try:
    level_model = joblib.load(LEVEL_MODEL_PATH)
    risk_model  = joblib.load(RISK_MODEL_PATH)
    scaler      = joblib.load(SCALER_PATH)
    print("[ML] Models loaded successfully")
except Exception as e:
    print(f"[ML] Model load error (using fallback): {e}")
    level_model = risk_model = scaler = None


# =========================
# ML PREDICTION HELPERS
# =========================
def predict_learner_level(features: dict) -> str:
    try:
        if level_model is None or scaler is None:
            overall = features.get("overall_score", 0)
            return "Strong" if overall >= 70 else ("Average" if overall >= 40 else "Weak")

        recognized = [
            "overall_score", "quiz_average", "assignment_average",
            "completion_rate", "avg_watch_time", "quiz_attempt_rate",
            "assignment_submission_rate", "videos_completed",
            "quizzes_attempted", "assignments_submitted", "total_course_items"
        ]
        clean = {f: features.get(f, 0) for f in recognized}
        df     = pd.DataFrame([clean])
        scaled = scaler.transform(df)
        pred   = level_model.predict(scaled)[0]
        
        # Handle numeric labels if they exist
        if isinstance(pred, (int, np.integer)):
             levels = {0: "Weak", 1: "Average", 2: "Strong"}
             return levels.get(int(pred), "Average")

        return str(pred) # Ensure it's a standard Python string
    except Exception as e:
        print(f"[ML Level Prediction Error] {e}")
        overall = features.get("overall_score", 0)
        return "Strong" if overall >= 70 else ("Average" if overall >= 40 else "Weak")

def predict_dropout_risk(features: dict) -> str:
    try:
        if risk_model is None or scaler is None:
            overall = features.get("overall_score", 0)
            return "High" if overall < 40 else ("Medium" if overall < 70 else "Low")

        recognized = [
            "overall_score", "quiz_average", "assignment_average",
            "completion_rate", "avg_watch_time", "quiz_attempt_rate",
            "assignment_submission_rate", "videos_completed",
            "quizzes_attempted", "assignments_submitted", "total_course_items"
        ]
        clean = {f: features.get(f, 0) for f in recognized}
        df     = pd.DataFrame([clean])
        scaled = scaler.transform(df)
        pred   = risk_model.predict(scaled)[0]
        
        # If the model returns 0/1 instead of strings, map them
        if isinstance(pred, (int, np.integer, float, pd.api.types.is_integer_dtype, pd.api.types.is_float_dtype)):
            return "High" if int(pred) == 1 else "Low"
            
        return str(pred) # Ensure it's a standard Python string
    except Exception as e:
        print(f"[ML Risk Prediction Error] {e}")
        overall = features.get("overall_score", 0)
        return "High" if overall < 40 else ("Medium" if overall < 70 else "Low")


# =========================
# ROUTER SETUP
# =========================
router = APIRouter(prefix="/api/v1/student", tags=["Student"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_student(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Student access required")
    return current_user

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

if not GROQ_API_KEY:
    print("[student.py] ERROR: GROQ_API_KEY empty — check backend/.env")
else:
    print(f"[student.py] GROQ key: {GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:]}")


# ────────────────────────────────────────────
#  COURSES
# ────────────────────────────────────────────

@router.get("/courses")
def get_student_courses(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    results = db.query(models.Course, models.User.name.label("teacher_name")).join(
        models.User, models.Course.created_by == models.User.id
    ).filter(
        models.Course.organization_id == current_user.organization_id,
        models.Course.status == True
    ).all()

    return [{
        "id": c.id, "title": c.title, "description": c.description,
        "difficulty": c.difficulty, "logo": c.logo, "status": c.status,
        "teacher_name": teacher_name
    } for c, teacher_name in results]


@router.get("/enrollments")
def get_enrollments(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    enrollments = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_user.id
    ).all()

    # A course is "completed" when an issued certificate exists for it
    issued_course_ids = {
        c.course_id for c in db.query(models.Certificate).filter(
            models.Certificate.student_id == current_user.id,
            models.Certificate.issued     == True
        ).all()
    }

    return [
        {
            "id":        e.id,
            "course_id": e.course_id,
            "completed": e.course_id in issued_course_ids
        }
        for e in enrollments
    ]


@router.post("/courses/{course_id}/enroll")
def enroll_course(
    course_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == current_user.organization_id
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_user.id,
        models.Enrollment.course_id  == course_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already enrolled")

    e = models.Enrollment(student_id=current_user.id, course_id=course_id)
    db.add(e); db.commit(); db.refresh(e)

    # Notify Teacher
    create_notification(
        db, course.created_by,
        "New Enrollment",
        f"Student {current_user.name} has enrolled in your course '{course.title}'.",
        f"student-detail.html?id={current_user.id}"
    )

    return {"message": "Enrolled successfully", "enrollment_id": e.id}


@router.get("/courses/{course_id}/stats")
def get_course_stats(
    course_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == current_user.organization_id
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    topic_ids = [t.id for t in
                 db.query(models.Topic.id).filter(models.Topic.course_id == course_id).all()]

    total_quizzes     = db.query(models.Quiz).filter(
        models.Quiz.topic_id.in_(topic_ids)).count() if topic_ids else 0
    total_assignments = db.query(models.Assignment).filter(
        models.Assignment.topic_id.in_(topic_ids)).count() if topic_ids else 0

    return {
        "total_topics":      len(topic_ids),
        "total_quizzes":     total_quizzes,
        "total_assignments": total_assignments
    }


@router.get("/courses/{course_id}/detail")
def get_course_detail(
    course_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == current_user.organization_id
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    is_enrolled = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == current_user.id,
        models.Enrollment.course_id  == course_id
    ).first() is not None

    # Certificate info
    cert = db.query(models.Certificate).filter(
        models.Certificate.student_id == current_user.id,
        models.Certificate.course_id  == course_id
    ).first()

    topics = db.query(models.Topic).filter(
        models.Topic.course_id == course_id
    ).order_by(models.Topic.order_number).all()

    topics_data = []
    for t in topics:
        videos      = db.query(models.Video).filter(models.Video.topic_id == t.id).all()
        quizzes     = db.query(models.Quiz).filter(models.Quiz.topic_id == t.id).all()
        assignments = db.query(models.Assignment).filter(
            models.Assignment.topic_id == t.id).all()

        topics_data.append({
            "id": t.id, "title": t.title, "order_number": t.order_number,
            "videos":      [{"id": v.id, "video_url": v.video_url,
                             "duration": v.duration} for v in videos],
            "quizzes":     [{"id": q.id, "title": q.title} for q in quizzes],
            "assignments": [{"id": a.id, "title": a.title,
                             "total_marks": a.total_marks} for a in assignments]
        })

    return {
        "id": course.id, "title": course.title,
        "description": course.description,
        "difficulty":  course.difficulty,
        "logo":        course.logo,
        "is_enrolled": is_enrolled,
        "cert_id": getattr(cert, "id", None),
        "cert_status": getattr(cert, "status", None),
        "cert_issued": getattr(cert, "issued", False),
        "topics":      topics_data
    }


@router.get("/my-courses")
def get_my_enrolled_courses(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    # Join Enrollments with Courses
    results = db.query(models.Course).join(
        models.Enrollment, models.Enrollment.course_id == models.Course.id
    ).filter(
        models.Enrollment.student_id == current_user.id
    ).all()

    return results

# ────────────────────────────────────────────
#  CERTIFICATES (with Auto-Request logic)
# ────────────────────────────────────────────

def check_and_auto_request_certificate(db: Session, student_id: int, course_id: int):
    """
    Internal helper: Checks if student meets all criteria.
    If yes, creates or updates a PENDING certificate record.
    """
    # 1. Check if already exists
    existing = db.query(models.Certificate).filter(
        models.Certificate.student_id == student_id,
        models.Certificate.course_id  == course_id
    ).first()
    
    # If it's already pending or issued, do nothing
    if existing and (existing.status == "pending" or existing.issued):
        return

    # 2. Get all topic IDs
    topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course_id).all()]
    if not topic_ids: return

    # 3. Check Videos (100% completion)
    video_ids = [v[0] for v in db.query(models.Video.id).filter(models.Video.topic_id.in_(topic_ids)).all()]
    if video_ids:
        watched_count = db.query(models.VideoProgress).filter(
            models.VideoProgress.student_id == student_id,
            models.VideoProgress.video_id.in_(video_ids),
            models.VideoProgress.watch_percentage >= 80
        ).count()
        if watched_count < len(video_ids): return

    # 4. Check Quizzes (All attempted)
    quiz_ids = [q[0] for q in db.query(models.Quiz.id).filter(models.Quiz.topic_id.in_(topic_ids)).all()]
    if quiz_ids:
        attempted = {a[0] for a in db.query(models.QuizAttempt.quiz_id).filter(
            models.QuizAttempt.student_id == student_id,
            models.QuizAttempt.quiz_id.in_(quiz_ids)
        ).all()}
        if len(attempted) < len(quiz_ids): return

    # 5. Check Assignments (All submitted)
    assign_ids = [a[0] for a in db.query(models.Assignment.id).filter(models.Assignment.topic_id.in_(topic_ids)).all()]
    if assign_ids:
        submitted = {s.assignment_id for s in db.query(models.AssignmentSubmission.assignment_id).filter(
            models.AssignmentSubmission.student_id == student_id,
            models.AssignmentSubmission.assignment_id.in_(assign_ids)
        ).all()}
        if len(submitted) < len(assign_ids): return

    # 6. Criteria Met! Create or Update request
    student = db.query(models.User).filter(models.User.id == student_id).first()
    
    if existing:
        existing.status = "pending"
        existing.request_date = datetime.utcnow()
    else:
        new_cert = models.Certificate(
            student_id=student_id, course_id=course_id,
            status="pending", eligible=True
        )
        db.add(new_cert)
    
    db.commit()
    
    # Notify Student and Admin
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    create_notification(
        db, student_id,
        "Eligibility Achieved! 🎓",
        f"You have completed all requirements for {course.title if course else 'your course'}. A certificate request has been sent to the admin.",
        "student-performnace.html"
    )
    
    # Find Admin(s) and Course Teacher
    org_id = course.organization_id if course else None
    if org_id:
        admins = db.query(models.User.id).filter(models.User.organization_id == org_id, models.User.role == "admin").all()
        for (aid,) in admins:
            create_notification(
                db, aid,
                "New Certificate Request",
                f"A student has completed {course.title if course else 'a course'} and is requesting a certificate.",
                "certificates.html"
            )
    
    # Notify Teacher specifically
    if course and course.created_by:
        student_name = student.name if student else "A student"
        create_notification(
            db, course.created_by,
            "Student Course Completion",
            f"Your student {student_name} has completed '{course.title}' and requested a certificate.",
            "certificates.html"
        )

    print(f"[Auto-Cert] Created/Updated request for Student {student_id} in Course {course_id}")

@router.post("/courses/{course_id}/request-certificate")
def request_certificate(
    course_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(get_current_student)
):
    existing = db.query(models.Certificate).filter(
        models.Certificate.student_id == student.id,
        models.Certificate.course_id  == course_id
    ).first()
    
    if existing:
        if existing.issued:
            return {"message": "Certificate already issued", "status": "verified"}
        if existing.status == "pending":
            return {"message": "Request already exists and is pending", "status": "pending"}
        # If status is rejected, we allow re-request below

    # ── Get all topic IDs for this course ──────────────────────────────────
    topic_ids = [t[0] for t in
                 db.query(models.Topic.id).filter(models.Topic.course_id == course_id).all()]

    if not topic_ids:
        raise HTTPException(status_code=400,
                            detail="This course has no content yet.")

    # ── Check 1: All videos watched >= 80% ────────────────────────────────
    video_ids = [v[0] for v in
                 db.query(models.Video.id).filter(models.Video.topic_id.in_(topic_ids)).all()]

    if video_ids:
        watched_count = db.query(models.VideoProgress).filter(
            models.VideoProgress.student_id      == student.id,
            models.VideoProgress.video_id.in_(video_ids),
            models.VideoProgress.watch_percentage >= 80
        ).count()
        if watched_count < len(video_ids):
            raise HTTPException(
                status_code=400,
                detail=f"Complete all videos first — watched {watched_count} of {len(video_ids)}."
            )

    # ── Check 2: All quizzes attempted ────────────────────────────────────
    quiz_ids = [q[0] for q in
                db.query(models.Quiz.id).filter(models.Quiz.topic_id.in_(topic_ids)).all()]

    if quiz_ids:
        attempted_quiz_ids = {
            a[0] for a in db.query(models.QuizAttempt.quiz_id).filter(
                models.QuizAttempt.student_id == student.id,
                models.QuizAttempt.quiz_id.in_(quiz_ids)
            ).all()
        }
        if len(attempted_quiz_ids) < len(quiz_ids):
            raise HTTPException(
                status_code=400,
                detail=f"Attempt all quizzes first — completed {len(attempted_quiz_ids)} of {len(quiz_ids)}."
            )

    # ── Check 3: All assignments submitted ────────────────────────────────
    assign_ids = [a[0] for a in
                  db.query(models.Assignment.id).filter(
                      models.Assignment.topic_id.in_(topic_ids)).all()]

    if assign_ids:
        submitted_assign_ids = {
            s.assignment_id for s in db.query(models.AssignmentSubmission.assignment_id).filter(
                models.AssignmentSubmission.student_id == student.id,
                models.AssignmentSubmission.assignment_id.in_(assign_ids)
            ).all()
        }
        if len(submitted_assign_ids) < len(assign_ids):
            raise HTTPException(
                status_code=400,
                detail=f"Submit all assignments first — submitted {len(submitted_assign_ids)} of {len(assign_ids)}."
            )

    # ── All checks passed → create certificate request ────────────────────
    new_cert = models.Certificate(
        student_id=student.id, course_id=course_id,
        status="pending", eligible=True
    )
    db.add(new_cert); db.commit()

    # Notify Admin(s) and Course Teacher
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    org_id = course.organization_id if course else None
    if org_id:
        admins = db.query(models.User.id).filter(models.User.organization_id == org_id, models.User.role == "admin").all()
        for (aid,) in admins:
            create_notification(
                db, aid,
                "New Certificate Request",
                f"Student {student.name} is requesting a certificate for '{course.title if course else 'a course'}'.",
                "certificates.html"
            )
    
    if course and course.created_by:
        create_notification(
            db, course.created_by,
            "Student Certificate Request",
            f"Your student {student.name} has requested a certificate for '{course.title}'.",
            "certificates.html"
        )

    return {"message": "Certificate request submitted.", "status": "pending"}


@router.get("/certificates")
def get_my_certificates(
    db: Session = Depends(get_db),
    student: models.User = Depends(get_current_student)
):
    certs = db.query(models.Certificate, models.Course.title)\
        .join(models.Course)\
        .filter(models.Certificate.student_id == student.id).all()

    return [{
        "id":           c.id,
        "course_title": title,
        "status":       c.status,
        "issued":       c.issued,
        "issued_at":    c.issued_at.isoformat() if c.issued_at else None,
        "request_date": c.request_date.isoformat() if c.request_date else None
    } for c, title in certs]


@router.get("/certificates/{cert_id}/download")
def download_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(get_current_student)
):
    cert = db.query(models.Certificate).filter(
        models.Certificate.id         == cert_id,
        models.Certificate.student_id == student.id,
        models.Certificate.issued     == True
    ).first()
    if not cert:
        raise HTTPException(status_code=404,
                            detail="Certificate not found or not yet issued.")

    course = db.query(models.Course).filter(models.Course.id == cert.course_id).first()
    org    = db.query(models.Organization).filter(
        models.Organization.id == student.organization_id).first()

    try:
        from certificate_generator import generate_certificate_pdf
        pdf_buffer = generate_certificate_pdf(
            student_name=student.name,
            course_name=course.title,
            org_name=org.platform_name or org.name,
            logo_url=org.logo,
            signature_url=org.signature_url,
            issue_date=cert.issued_at.strftime("%B %d, %Y")
        )
        safe_course = "".join(
            ch for ch in course.title.replace(" ", "_")
            if ord(ch) < 128 and ch not in r'\\/:*?"<>|'
        ) or "Course"
        headers = {
            'Content-Disposition':
                f'attachment; filename="Certificate_{safe_course}.pdf"'
        }
        return StreamingResponse(pdf_buffer, headers=headers,
                                 media_type='application/pdf')
    except ImportError:
        raise HTTPException(status_code=500,
                            detail="Certificate generator not available.")


# ────────────────────────────────────────────
#  VIDEO PROGRESS
# ────────────────────────────────────────────

class VideoProgressIn(BaseModel):
    watch_time:       int
    watch_percentage: int
    skip_count:       Optional[int]   = 0
    playback_speed:   Optional[float] = 1.0


@router.post("/videos/{video_id}/progress")
def save_video_progress(
    video_id: int,
    data: VideoProgressIn,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    existing = db.query(models.VideoProgress).filter(
        models.VideoProgress.student_id == current_user.id,
        models.VideoProgress.video_id   == video_id
    ).first()

    if existing:
        if data.watch_percentage > (existing.watch_percentage or 0):
            existing.watch_percentage = data.watch_percentage
        if data.watch_time > (existing.watch_time or 0):
            existing.watch_time = data.watch_time
        existing.skip_count     = data.skip_count
        existing.playback_speed = data.playback_speed
    else:
        db.add(models.VideoProgress(
            student_id=current_user.id, video_id=video_id,
            watch_time=data.watch_time, watch_percentage=data.watch_percentage,
            skip_count=data.skip_count, playback_speed=data.playback_speed
        ))
    db.commit()

    # ── Auto-Request Check ──
    topic = db.query(models.Topic).join(models.Video).filter(models.Video.id == video_id).first()
    if topic:
        check_and_auto_request_certificate(db, current_user.id, topic.course_id)

    return {"message": "Progress saved"}


@router.get("/videos/{video_id}/progress")
def get_video_progress(
    video_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    p = db.query(models.VideoProgress).filter(
        models.VideoProgress.student_id == current_user.id,
        models.VideoProgress.video_id   == video_id
    ).first()
    if not p:
        return {"watch_time": 0, "watch_percentage": 0,
                "skip_count": 0, "playback_speed": 1.0}
    return {
        "watch_time":       p.watch_time,
        "watch_percentage": p.watch_percentage,
        "skip_count":       p.skip_count,
        "playback_speed":   p.playback_speed
    }


@router.get("/video-progress-all")
def get_all_video_progress(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    records = db.query(models.VideoProgress).filter(
        models.VideoProgress.student_id == current_user.id
    ).all()
    return [{
        "video_id":         r.video_id,
        "watch_time":       r.watch_time,
        "watch_percentage": r.watch_percentage
    } for r in records]


# ────────────────────────────────────────────
#  QUIZ ATTEMPTS
# ────────────────────────────────────────────

class AnswerItem(BaseModel):
    question_id:     int
    selected_option: Optional[str] = None

class QuizAttemptIn(BaseModel):
    answers: List[AnswerItem]


@router.get("/quiz-attempts")
def get_all_attempts(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    attempts = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == current_user.id
    ).all()
    result = []
    for a in attempts:
        q_count = db.query(models.QuizQuestion).filter(
            models.QuizQuestion.quiz_id == a.quiz_id
        ).count()
        pct = round((a.score / q_count) * 100, 2) if q_count > 0 else 0
        result.append({
            "id":           a.id,
            "quiz_id":      a.quiz_id,
            "score":        a.score,
            "total":        q_count,
            "percentage":   pct,
            "attempted_at": a.attempted_at
        })
    return result


@router.post("/quizzes/{quiz_id}/attempt")
def submit_quiz(
    quiz_id: int,
    payload: QuizAttemptIn,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    if db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == current_user.id,
        models.QuizAttempt.quiz_id    == quiz_id
    ).first():
        raise HTTPException(status_code=400, detail="Quiz already attempted")

    questions = db.query(models.QuizQuestion).filter(
        models.QuizQuestion.quiz_id == quiz_id
    ).all()
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found")

    correct_map   = {q.id: q.correct_option.upper() for q in questions}
    total         = len(questions)
    correct_count = 0
    wrong_count   = 0
    skipped_count = 0

    for ans in payload.answers:
        sel = (ans.selected_option or "").strip().upper()
        if not sel:
            skipped_count += 1
        elif sel == correct_map.get(ans.question_id, ""):
            correct_count += 1
        else:
            wrong_count += 1

    attempt = models.QuizAttempt(
        student_id=current_user.id, quiz_id=quiz_id, score=correct_count
    )
    db.add(attempt); db.flush() # flush to get attempt.id

    # Save answers
    for ans in payload.answers:
        db.add(models.QuizAttemptAnswer(
            attempt_id=attempt.id,
            question_id=ans.question_id,
            selected_option=ans.selected_option
        ))

    db.commit(); db.refresh(attempt)

    # ── Auto-Request Check ──
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if quiz:
        topic = db.query(models.Topic).filter(models.Topic.id == quiz.topic_id).first()
        if topic:
            check_and_auto_request_certificate(db, current_user.id, topic.course_id)

    return {
        "attempt_id":      attempt.id,
        "score":           correct_count,
        "total_questions": total,
        "correct_answers": correct_count,
        "wrong_answers":   wrong_count,
        "skipped":         skipped_count,
        "percentage":      round((correct_count / total) * 100, 2) if total > 0 else 0
    }

@router.get("/quizzes/{quiz_id}/review")
def review_quiz(
    quiz_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == current_user.id,
        models.QuizAttempt.quiz_id == quiz_id
    ).order_by(models.QuizAttempt.attempted_at.desc()).first()

    if not attempt:
        raise HTTPException(status_code=404, detail="No attempt found for this quiz")

    questions = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == quiz_id).all()
    answers = db.query(models.QuizAttemptAnswer).filter(models.QuizAttemptAnswer.attempt_id == attempt.id).all()
    ans_map = {a.question_id: a.selected_option for a in answers}

    review_data = []
    for q in questions:
        review_data.append({
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "selected_option": ans_map.get(q.id)
        })

    return {
        "quiz_id": quiz_id,
        "score": attempt.score,
        "total": len(questions),
        "attempted_at": attempt.attempted_at,
        "questions": review_data
    }



# ────────────────────────────────────────────
#  AI GRADING
# ────────────────────────────────────────────

class AssignmentSubmitIn(BaseModel):
    student_answer: str


def grade_with_ai(question: str, model_answer: str,
                  student_answer: str, total_marks: int) -> Optional[dict]:
    if not GROQ_API_KEY:
        return None

    if model_answer and model_answer.strip():
        grading_instruction = (
            f"Grade strictly based on these model answer keywords: {model_answer}\n"
            "Check if the student's answer covers these concepts."
        )
    else:
        grading_instruction = (
            "Grade based on your own knowledge of the subject.\n"
            "Evaluate correctness, completeness, and code quality."
        )

    json_format = ('{"obtained_marks": <integer 0-' + str(total_marks) +
                   '>, "feedback": "<one clear sentence>"}')
    prompt = (
        "You are an expert programming and computer science assignment grader.\n\n"
        f"Question: {question}\n"
        f"{grading_instruction}\n\n"
        f"Student Answer:\n{student_answer}\n\n"
        f"Total Marks: {total_marks}\n\n"
        f"Return ONLY valid JSON, no markdown, no extra text:\n"
        f"{json_format}"
    )

    try:
        res = http_requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": GROQ_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1},
            timeout=30
        )
        if res.status_code != 200:
            print(f"[Groq] error: {res.text}")
            return None

        raw     = res.json()["choices"][0]["message"]["content"].strip()
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        result  = json.loads(cleaned)
        return {
            "obtained_marks": max(0, min(int(result.get("obtained_marks", 0)), total_marks)),
            "feedback":       str(result.get("feedback", ""))
        }
    except Exception as e:
        print(f"[Groq] Exception: {e}")
        return None


# ────────────────────────────────────────────
#  ASSIGNMENT ENDPOINTS
# ────────────────────────────────────────────

@router.get("/assignment-submissions")
def get_submissions(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    subs = db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.student_id == current_user.id
    ).order_by(models.AssignmentSubmission.id.asc()).all()

    grouped = defaultdict(list)
    for s in subs:
        grouped[s.assignment_id].append(s)

    result = []
    for assignment_id, attempts in grouped.items():
        best = max(attempts, key=lambda x: x.obtained_marks or 0)
        result.append({
            "id":             best.id,
            "assignment_id":  assignment_id,
            "obtained_marks": best.obtained_marks,
            "feedback":       getattr(best, "feedback", None),
            "is_manual_review": getattr(best, "is_manual_review", False),
            "submitted_at":   best.submitted_at,
            "attempt_count":  len(attempts),
            "can_resubmit":   len(attempts) < 2
        })
    return result


@router.get("/assignments/{assignment_id}")
def get_assignment_detail(
    assignment_id: int,
    current_user:  models.User = Depends(get_current_student),
    db: Session    = Depends(get_db)
):
    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    topic  = db.query(models.Topic).filter(
        models.Topic.id == assignment.topic_id).first()
    course = db.query(models.Course).filter(
        models.Course.id == topic.course_id).first() if topic else None

    return {
        "id":           assignment.id,
        "title":        assignment.title,
        "description":  assignment.description,
        "total_marks":  assignment.total_marks,
        "file_url":     assignment.file_url,
        "topic_title":  topic.title  if topic  else "",
        "course_title": course.title if course else ""
    }


@router.post("/assignments/{assignment_id}/submit")
def submit_assignment(
    assignment_id: int,
    payload:       AssignmentSubmitIn,
    current_user:  models.User = Depends(get_current_student),
    db: Session    = Depends(get_db)
):
    attempt_count = db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.student_id    == current_user.id,
        models.AssignmentSubmission.assignment_id == assignment_id
    ).count()
    if attempt_count >= 2:
        raise HTTPException(status_code=400, detail="Maximum 2 submissions reached")

    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    grading = grade_with_ai(
        question=      assignment.title,
        model_answer=  assignment.model_answer or "",
        student_answer=payload.student_answer,
        total_marks=   assignment.total_marks or 10
    )

    is_manual = False
    if grading is None:
        is_manual = True
        grading = {"obtained_marks": 0, "feedback": "AI grading failed. Waiting for teacher review."}

    submission = models.AssignmentSubmission(
        student_id=current_user.id,
        assignment_id=assignment_id,
        student_answer=payload.student_answer,
        obtained_marks=grading["obtained_marks"],
        feedback=grading["feedback"],
        is_manual_review=is_manual
    )
    db.add(submission); db.commit(); db.refresh(submission)

    # ── Notify Teacher if manual review needed ──
    if is_manual:
        topic = db.query(models.Topic).filter(models.Topic.id == assignment.topic_id).first()
        if topic:
            course = db.query(models.Course).filter(models.Course.id == topic.course_id).first()
            if course and course.created_by:
                create_notification(
                    db, course.created_by,
                    "Manual Grading Required",
                    f"AI grading failed for {current_user.name}'s assignment '{assignment.title}'. Please grade manually.",
                    f"student-detail.html?id={current_user.id}"
                )

    # ── Auto-Request Check (Only if AI succeeded) ──
    if not is_manual:
        topic = db.query(models.Topic).filter(models.Topic.id == assignment.topic_id).first()
        if topic:
            check_and_auto_request_certificate(db, current_user.id, topic.course_id)

    return {
        "submission_id":  submission.id,
        "obtained_marks": grading["obtained_marks"],
        "total_marks":    assignment.total_marks,
        "feedback":       grading["feedback"],
        "is_manual_review": is_manual
    }


# ────────────────────────────────────────────
#  PERFORMANCE UPDATE (with ML prediction)
# ────────────────────────────────────────────

@router.get("/skill-gap/{course_id}")
def get_skill_gap_analysis(
    course_id: int,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    # 1. Get Course Topics
    topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).all()
    if not topics:
        raise HTTPException(status_code=404, detail="No topics found for this course")

    # 2. Gather topic-wise performance
    analysis_data = []
    for t in topics:
        # Get quizzes for this topic
        quizzes = db.query(models.Quiz).filter(models.Quiz.topic_id == t.id).all()
        quiz_scores = []
        for q in quizzes:
            attempt = db.query(models.QuizAttempt).filter(
                models.QuizAttempt.student_id == current_user.id,
                models.QuizAttempt.quiz_id == q.id
            ).first()
            if attempt:
                # Find total questions for this quiz
                q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == q.id).count()
                if q_count > 0:
                    quiz_scores.append((attempt.score / q_count) * 100)

        # Get assignments for this topic
        assignments = db.query(models.Assignment).filter(models.Assignment.topic_id == t.id).all()
        assign_scores = []
        for a in assignments:
            sub = db.query(models.AssignmentSubmission).filter(
                models.AssignmentSubmission.student_id == current_user.id,
                models.AssignmentSubmission.assignment_id == a.id
            ).order_by(models.AssignmentSubmission.obtained_marks.desc()).first()
            if sub:
                assign_scores.append((sub.obtained_marks / (a.total_marks or 10)) * 100)

        avg_score = None
        combined = quiz_scores + assign_scores
        if combined:
            avg_score = sum(combined) / len(combined)

        analysis_data.append({
            "topic_title": t.title,
            "avg_score": avg_score,
            "status": "Attempted" if combined else "Not Attempted"
        })

    # 3. AI Analysis with Llama-3 (Groq)
    perf_summary = json.dumps(analysis_data)
    
    # Check if student is struggling
    struggling = any(d["avg_score"] is not None and d["avg_score"] < 60 for d in analysis_data)
    
    prompt = f"""
    Analyze the following student performance data and provide a Personal Recovery Plan.
    Data: {perf_summary}

    If the student has scores < 60% or many 'Not Attempted' topics, be firm but encouraging.
    
    Requirements:
    1. Identify 'Strengths' (topics where score > 80%).
    2. Identify 'Weaknesses' (topics where score < 60% or 'Not Attempted').
    3. For EACH Weakness, provide a specific 'Recovery Action' (e.g., 'Watch Topic X video again focus on Y', 'Read material Z').
    4. Generate a 'Mini-Review Guide': A short (2-sentence) summary of the core concept the student is missing in their weakest topic.
    5. Provide a 'Motivation Message' that acknowledges their current struggles but shows a clear path to success.

    Return ONLY a valid JSON object:
    {{
      "strengths": ["...", "..."],
      "weaknesses": ["...", "..."],
      "recovery_plan": [
          {{"topic": "Topic Name", "action": "Specific remedial action", "video_suggestion": "Timestamp or specific sub-topic to re-watch"}}
      ],
      "review_guide": "...",
      "motivation": "..."
    }}
    """

    try:
        chat_completion = http_requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            },
            timeout=30
        )
        if chat_completion.status_code != 200:
            return {"error": "AI analysis unavailable"}
        
        result = chat_completion.json()["choices"][0]["message"]["content"]
        return json.loads(result)
    except Exception as e:
        print(f"[Skill-Gap Error] {e}")
        return {"error": "Analysis failed"}

@router.post("/update-performance")
def update_student_performance(
    data: schemas.StudentPerformanceUpdate,
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    perf = db.query(models.StudentPerformanceSummary).filter(
        models.StudentPerformanceSummary.student_id == current_user.id
    ).first()

    if not perf:
        perf = models.StudentPerformanceSummary(student_id=current_user.id)
        db.add(perf)

    # Update all fields
    fields = [
        "overall_score", "quiz_average", "assignment_average",
        "completion_rate", "avg_watch_time", "quiz_attempt_rate",
        "assignment_submission_rate", "videos_completed",
        "quizzes_attempted", "assignments_submitted", "total_course_items"
    ]
    for field in fields:
        val = getattr(data, field, None)
        if val is not None and hasattr(perf, field):
            setattr(perf, field, val)

    # ML predictions (Backend as Source of Truth)
    features = data.model_dump()
    level = predict_learner_level(features)
    risk  = predict_dropout_risk(features)
    
    perf.learner_level = level
    perf.dropout_risk = risk

    # global level if flagged
    if getattr(data, "is_global", False) and hasattr(perf, "global_learner_level"):
        perf.global_learner_level = level

    db.commit()
    return {"message": "Performance updated successfully", "level": level, "risk": risk}


# ────────────────────────────────────────────
#  PROFILE & ACCOUNT
# ────────────────────────────────────────────

@router.get("/profile")
def get_student_profile(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    return {
        "id":    current_user.id,
        "name":  current_user.name,
        "email": current_user.email,
        "role":  current_user.role
    }


@router.put("/profile")
def update_student_profile(
    name:             str = Form(None),
    email:            str = Form(None),
    password:         str = Form(None),
    current_password: str = Form(None),
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()

    if name:  user.name  = name
    if email: user.email = email

    if password:
        if not current_password:
            raise HTTPException(status_code=400, detail="Current password required")
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password incorrect")

        user.password_hash = hash_password(password)
    db.commit(); db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email}


@router.delete("/account")
def delete_student_account(
    current_user: models.User = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    sid = current_user.id

    db.query(models.QuizAttempt).filter(
        models.QuizAttempt.student_id == sid).delete()
    db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.student_id == sid).delete()
    db.query(models.Enrollment).filter(
        models.Enrollment.student_id == sid).delete()

    try:
        db.query(models.VideoProgress).filter(
            models.VideoProgress.student_id == sid).delete()
    except Exception:
        pass

    try:
        db.query(models.StudentPerformanceSummary).filter(
            models.StudentPerformanceSummary.student_id == sid).delete()
    except Exception:
        pass

    db.query(models.User).filter(models.User.id == sid).delete()
    db.commit()
    return {"message": "Account deleted successfully"}