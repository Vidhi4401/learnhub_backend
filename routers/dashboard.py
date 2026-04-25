from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, os
from datetime import datetime
from dependencies import get_current_teacher
from typing import Optional

router = APIRouter(prefix="/api/v1/teacher", tags=["Dashboard"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def get_dashboard(
    current_user: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    org_id = current_user.organization_id

    courses = db.query(models.Course).filter(
        models.Course.organization_id == org_id
    ).all()
    course_ids = [c.id for c in courses]

    topic_ids = []
    if course_ids:
        topics = db.query(models.Topic).filter(
            models.Topic.course_id.in_(course_ids)
        ).all()
        topic_ids = [t.id for t in topics]

    total_quizzes = db.query(models.Quiz).filter(
        models.Quiz.topic_id.in_(topic_ids)
    ).count() if topic_ids else 0

    total_assignments = db.query(models.Assignment).filter(
        models.Assignment.topic_id.in_(topic_ids)
    ).count() if topic_ids else 0

    enrolled_count = db.query(models.Enrollment.student_id).filter(
     models.Enrollment.course_id.in_(course_ids)
    ).distinct().count() if course_ids else 0

    org_student_count = db.query(models.User).filter(
    models.User.organization_id == org_id,
    models.User.role == "student"
).count()

# ── Use enrolled if exists, else org total ──
    if enrolled_count > 0:
     total_students  = enrolled_count
     students_label  = "Enrolled Students"
    else:
      total_students  = org_student_count
      students_label  = "Total Students"

    total_students = enrolled_count if enrolled_count > 0 else org_student_count

    certificates_issued = db.query(models.Certificate).filter(
        models.Certificate.course_id.in_(course_ids),
        models.Certificate.issued == True
    ).count() if course_ids else 0

    total_materials = db.query(models.Material).filter(
        models.Material.course_id.in_(course_ids)
    ).count() if course_ids else 0

    # ── Real Engagement Metrics ──
    # 1. Video Completion Rate
    total_videos = db.query(models.Video).join(models.Topic).filter(models.Topic.course_id.in_(course_ids)).count() if course_ids else 0
    total_enrolled = db.query(models.Enrollment).filter(models.Enrollment.course_id.in_(course_ids)).count() if course_ids else 0
    potential_views = total_videos * total_enrolled
    
    actual_completions = db.query(models.VideoProgress).join(models.Video).join(models.Topic).filter(
        models.Topic.course_id.in_(course_ids),
        models.VideoProgress.watch_percentage >= 80
    ).count() if course_ids else 0
    
    video_rate = round((actual_completions / potential_views * 100), 1) if potential_views > 0 else 0

    # 2. Quiz Attempt Rate
    total_quizzes = db.query(models.Quiz).join(models.Topic).filter(models.Topic.course_id.in_(course_ids)).count() if course_ids else 0
    potential_quizzes = total_quizzes * total_enrolled
    actual_attempts = db.query(models.QuizAttempt).join(models.Quiz).join(models.Topic).filter(models.Topic.course_id.in_(course_ids)).count() if course_ids else 0
    quiz_rate = round((actual_attempts / potential_quizzes * 100), 1) if potential_quizzes > 0 else 0

    # 3. Assignment Submission Rate
    total_assigns = db.query(models.Assignment).join(models.Topic).filter(models.Topic.course_id.in_(course_ids)).count() if course_ids else 0
    potential_assigns = total_assigns * total_enrolled
    actual_subs = db.query(models.AssignmentSubmission).join(models.Assignment).join(models.Topic).filter(models.Topic.course_id.in_(course_ids)).count() if course_ids else 0
    assign_rate = round((actual_subs / potential_assigns * 100), 1) if potential_assigns > 0 else 0

    return {
        "total_students":  total_students,
        "students_label":  students_label,
        "total_courses":   len(course_ids),
        "total_quizzes":   total_quizzes,
        "total_assignments":   total_assigns,
        "total_materials":     total_materials,
        "certificates_issued": certificates_issued,
        "engagement": {
            "video_rate": video_rate,
            "quiz_rate": quiz_rate,
            "assign_rate": assign_rate
        }
    }

from sqlalchemy import func
from routers.student import predict_learner_level

import joblib
import pandas as pd
import numpy as np

# ── Absolute path to /backend/ml/ regardless of CWD ──
_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))          # .../routers/
_ML_DIR     = os.path.join(os.path.dirname(_ROUTER_DIR), "ml")   # .../ml/

def _load_pkl(filename):
    path = os.path.join(_ML_DIR, filename)
    return joblib.load(path)

try:
    risk_model         = _load_pkl("final_risk_model.pkl")
    risk_scaler        = _load_pkl("final_scaler.pkl")
    model_feature_names = _load_pkl("model_features.pkl")
    print("[ML] Risk model loaded successfully")
except Exception as e:
    print(f"[ML Load Error] {e}")
    risk_model = risk_scaler = model_feature_names = None

def get_student_metrics(db: Session, student_id: int, course_id: int = None):
    """
    Check pre-calculated StudentPerformanceSummary table first.
    If course_id is provided, or summary doesn't exist, calculate from raw DB tables.
    """
    # ── 1. Check Pre-calculated Summary (Global view) ──
    if course_id is None:
        perf = db.query(models.StudentPerformanceSummary).filter(
            models.StudentPerformanceSummary.student_id == student_id
        ).first()
        if perf:
            metrics = {
                "overall_score": perf.overall_score or 0,
                "quiz_average": perf.quiz_average or 0,
                "assignment_average": perf.assignment_average or 0,
                "completion_rate": perf.completion_rate or 0,
                "avg_watch_time": perf.avg_watch_time or 0,
                "quiz_attempt_rate": perf.quiz_attempt_rate or 0,
                "assignment_submission_rate": perf.assignment_submission_rate or 0,
                "videos_completed": perf.videos_completed or 0,
                "quizzes_attempted": perf.quizzes_attempted or 0,
                "assignments_submitted": perf.assignments_submitted or 0,
                "total_course_items": perf.total_course_items or 0
            }
            return metrics, perf.learner_level or "Average", perf.dropout_risk or "Low"

    # ── 2. Fallback: Manual Calculation (Filtered or Missing) ──
    # 1. Filter Topics
    if course_id:
        topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course_id).all()]
    else:
        # Get ALL courses this specific student is enrolled in
        enrolled_course_ids = [e[0] for e in db.query(models.Enrollment.course_id).filter(models.Enrollment.student_id == student_id).all()]
        topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id.in_(enrolled_course_ids)).all()] if enrolled_course_ids else []
    
    if not topic_ids:
        return {k: 0.0 for k in ["overall_score", "quiz_average", "assignment_average", "completion_rate", "avg_watch_time", "quiz_attempt_rate", "assignment_submission_rate", "videos_completed", "quizzes_attempted", "assignments_submitted", "total_course_items"]}, "Weak", "High"

    # 2. Denominators
    total_vids = db.query(models.Video).filter(models.Video.topic_id.in_(topic_ids)).count()
    total_quizzes = db.query(models.Quiz).filter(models.Quiz.topic_id.in_(topic_ids)).count()
    total_assigns = db.query(models.Assignment).filter(models.Assignment.topic_id.in_(topic_ids)).count()
    
    # 3. Student Activity
    attempts = db.query(models.QuizAttempt).join(models.Quiz).filter(
        models.QuizAttempt.student_id == student_id, models.Quiz.topic_id.in_(topic_ids)
    ).all()
    
    subs = db.query(models.AssignmentSubmission).join(models.Assignment).filter(
        models.AssignmentSubmission.student_id == student_id, models.Assignment.topic_id.in_(topic_ids)
    ).all()
    
    v_progs = db.query(models.VideoProgress).join(models.Video).filter(
        models.VideoProgress.student_id == student_id, models.Video.topic_id.in_(topic_ids)
    ).all()

    # 4. Feature Calculations
    q_avg = 0
    if attempts:
        q_scores = []
        for a in attempts:
            q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == a.quiz_id).count()
            if q_count > 0: q_scores.append((a.score / q_count) * 100)
        q_avg = min(100, sum(q_scores) / len(q_scores)) if q_scores else 0
    
    a_avg = 0
    if subs:
        a_scores = []
        for s in subs:
            total_m = db.query(models.Assignment.total_marks).filter(models.Assignment.id == s.assignment_id).scalar()
            if total_m and total_m > 0: a_scores.append((s.obtained_marks / total_m) * 100)
        a_avg = min(100, sum(a_scores) / len(a_scores)) if a_scores else 0
    
    distinct_attempts = len(set([a.quiz_id for a in attempts]))
    distinct_subs = len(set([s.assignment_id for s in subs]))
    comp_vids = len([p for p in v_progs if p.watch_percentage >= 80])
    
    v_comp_rate = min(100, (comp_vids / total_vids * 100)) if total_vids > 0 else 0
    avg_w_time = sum([p.watch_time for p in v_progs]) / len(v_progs) if v_progs else 0
    q_att_rate = min(100, (distinct_attempts / total_quizzes * 100)) if total_quizzes > 0 else 0
    a_sub_rate = min(100, (distinct_subs / total_assigns * 100)) if total_assigns > 0 else 0
    
    metrics_list = [m for m in [q_avg, a_avg, v_comp_rate] if m > 0]
    overall = sum(metrics_list) / len(metrics_list) if metrics_list else 0

    features = {
        "overall_score": float(overall),
        "quiz_average": float(q_avg),
        "assignment_average": float(a_avg),
        "completion_rate": float(v_comp_rate),
        "avg_watch_time": float(avg_w_time),
        "quiz_attempt_rate": float(q_att_rate),
        "assignment_submission_rate": float(a_sub_rate),
        "videos_completed": int(comp_vids),
        "quizzes_attempted": int(distinct_attempts),
        "assignments_submitted": int(distinct_subs),
        "total_course_items": int(total_vids + total_quizzes + total_assigns)
    }
    
    level = predict_learner_level(features)
    
    # 5. Predict Risk
    risk = "Low"
    if risk_model and model_feature_names and risk_scaler:
        try:
            feat_df = pd.DataFrame([features])[model_feature_names]
            scaled = risk_scaler.transform(feat_df)
            risk_pred = risk_model.predict(scaled)[0]
            # Handle numeric predictions (0=Low, 1=High) if model returns numbers
            if isinstance(risk_pred, (int, np.integer)):
                risk = "High" if int(risk_pred) == 1 else "Low"
            else:
                risk = str(risk_pred)
        except Exception as e:
            print(f"[ML Risk Prediction Error] {e}")
            risk = "High" if overall < 40 else ("Medium" if overall < 70 else "Low")
    else:
        # Better rule-based fallback when model is missing
        if overall < 40: risk = "High"
        elif overall < 70: risk = "Medium"
        else: risk = "Low"

    return features, level, risk

from fastapi.responses import StreamingResponse
import io

@router.get("/students")
def get_all_students(
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    # 1. Get IDs of courses owned/assigned to this teacher
    managed_course_ids = [c[0] for c in db.query(models.Course.id).filter(
        models.Course.organization_id == teacher.organization_id,
        models.Course.created_by == teacher.id
    ).all()]
    
    if not managed_course_ids:
        return []

    # 2. Find students enrolled in those courses (or specific course if provided)
    enrollment_query = db.query(models.Enrollment.student_id).filter(
        models.Enrollment.course_id.in_(managed_course_ids)
    )
    
    if course_id:
        if course_id not in managed_course_ids:
            return []  # Teacher doesn't manage this course
        enrollment_query = enrollment_query.filter(models.Enrollment.course_id == course_id)
    
    student_ids = [e[0] for e in enrollment_query.distinct().all()]
    
    if not student_ids:
        return []

    # 3. Fetch user details for those students
    students = db.query(models.User).filter(
        models.User.id.in_(student_ids)
    ).all()
    
    results = []
    for s in students:
        course_count = db.query(models.Enrollment).filter(models.Enrollment.student_id == s.id).count()
        features, level, risk = get_student_metrics(db, s.id)
        results.append({
            "id":            s.id,
            "name":          s.name,
            "email":         s.email,
            "course_count":  course_count,
            "overall_score": round(features["overall_score"], 1),
            "quiz_avg":      round(features["quiz_average"], 1),
            "assign_avg":    round(features["assignment_average"], 1),
            "learner_level": level,
            "dropout_risk":  risk
        })
    return results

@router.get("/students/export")
def export_students_excel(
    token: str = None,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    """Advanced multi-sheet Excel export for teacher's students."""
    students_data = get_all_students(db, teacher)
    if not students_data:
        raise HTTPException(status_code=400, detail="No student data to export")

    org = db.query(models.Organization).filter(
        models.Organization.id == teacher.organization_id
    ).first()
    org_name = (org.platform_name or org.name) if org else "LearnHub"

    from excel_export import build_teacher_report
    buf = build_teacher_report(
        students=students_data,
        teacher_name=teacher.name,
        org_name=org_name,
        db=db,
        get_student_metrics=get_student_metrics,
        models=models
    )

    safe_name = "".join(c for c in teacher.name.replace(" ", "_") if ord(c) < 128) or "Teacher"
    filename  = f"Students_Report_{safe_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    headers   = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, headers=headers,
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/students/{student_id}/detail")
def get_student_detail(
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    student = db.query(models.User).filter(
        models.User.id == student_id,
        models.User.organization_id == teacher.organization_id
    ).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    # 1. Global Metrics
    global_features, global_level, global_risk = get_student_metrics(db, student_id)

    # 2. Enrolled Courses with Course-Specific AI Levels
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.student_id == student_id).all()
    courses_data = []
    for enr in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enr.course_id).first()
        if not course: continue
        
        c_features, c_level, c_risk = get_student_metrics(db, student_id, course.id)
        
        # Format video string for UI (watched/total)
        topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course.id).all()]
        v_count = db.query(models.Video).filter(models.Video.topic_id.in_(topic_ids)).count() if topic_ids else 0

        total_quizzes_c = db.query(models.Quiz).filter(models.Quiz.topic_id.in_(topic_ids)).count() if topic_ids else 0
        total_assigns_c = db.query(models.Assignment).filter(models.Assignment.topic_id.in_(topic_ids)).count() if topic_ids else 0
        courses_data.append({
            "id":           course.id,
            "title":        course.title,
            "overall":      round(c_features["overall_score"], 1),
            "quiz_avg":     round(c_features["quiz_average"], 1),
            "assign_avg":   round(c_features["assignment_average"], 1),
            "completion_rate": round(c_features["completion_rate"], 1),
            "videos":       f"{c_features['videos_completed']}/{v_count}",
            "quizzes":      f"{c_features['quizzes_attempted']}/{total_quizzes_c}",
            "assignments":  f"{c_features['assignments_submitted']}/{total_assigns_c}",
            "level":        c_level,
            "risk":         c_risk
        })

    # 3. Detailed Video Progress (NEW)
    video_progress_data = []
    v_records = db.query(
        models.VideoProgress, 
        models.Video.video_url,
        models.Topic.title.label("topic_title"),
        models.Course.title.label("course_title")
    ).join(models.Video, models.VideoProgress.video_id == models.Video.id)\
     .join(models.Topic, models.Video.topic_id == models.Topic.id)\
     .join(models.Course, models.Topic.course_id == models.Course.id)\
     .filter(models.VideoProgress.student_id == student_id).all()
    
    for vp, v_url, t_title, c_title in v_records:
        video_progress_data.append({
            "course": c_title,
            "topic": t_title,
            "url": v_url,
            "watch_time": vp.watch_time,
            "percentage": vp.watch_percentage,
            "skip_count": getattr(vp, "skip_count", 0),
            "playback_speed": getattr(vp, "playback_speed", 1.0),
            "status": "Complete" if vp.watch_percentage >= 80 else "In Progress"
        })

    # 4. Recent Quiz Attempts
    attempts = db.query(models.QuizAttempt, models.Quiz.title, models.Course.title.label("course_title"))\
        .join(models.Quiz, models.QuizAttempt.quiz_id == models.Quiz.id)\
        .join(models.Topic, models.Quiz.topic_id == models.Topic.id)\
        .join(models.Course, models.Topic.course_id == models.Course.id)\
        .filter(models.QuizAttempt.student_id == student_id)\
        .order_by(models.QuizAttempt.attempted_at.desc()).limit(5).all()
    
    quiz_history = []
    for att, q_title, c_title in attempts:
        q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == att.quiz_id).count()
        quiz_history.append({
            "quiz": q_title, "course": c_title, "score": f"{att.score} / {q_count}",
            "pct": f"{round((att.score/q_count)*100) if q_count>0 else 0}%",
            "date": att.attempted_at.strftime("%b %d, %Y")
        })

    # 4. Recent Assignment Submissions
    subs = db.query(models.AssignmentSubmission, models.Assignment.title, models.Assignment.total_marks, models.Course.title.label("course_title"), models.Assignment.model_answer)\
        .join(models.Assignment, models.AssignmentSubmission.assignment_id == models.Assignment.id)\
        .join(models.Topic, models.Assignment.topic_id == models.Topic.id)\
        .join(models.Course, models.Topic.course_id == models.Course.id)\
        .filter(models.AssignmentSubmission.student_id == student_id)\
        .order_by(models.AssignmentSubmission.submitted_at.desc()).limit(10).all()
    
    assign_history = []
    for sub, a_title, t_marks, c_title, m_answer in subs:
        assign_history.append({
            "id": sub.id,
            "title": a_title,
            "course": c_title,
            "score": f"{sub.obtained_marks or 0} / {t_marks}",
            "pct": f"{round((sub.obtained_marks/t_marks)*100) if t_marks and sub.obtained_marks else 0}%",
            "date": sub.submitted_at.strftime("%b %d, %Y"),
            "student_answer": sub.student_answer,
            "model_answer": m_answer,
            "is_manual_review": sub.is_manual_review
        })

    return {
        "name":           student.name,
        "email":          student.email,
        "joined":         student.created_at.strftime("%B %d, %Y") if student.created_at else "—",
        "enrolled_count": len(enrollments),
        "overall_score":  round(global_features["overall_score"], 1),
        "quiz_average":   round(global_features["quiz_average"], 1),
        "assign_average": round(global_features["assignment_average"], 1),
        "completion_rate":round(global_features["completion_rate"], 1),
        "quiz_attempt_rate":      round(global_features["quiz_attempt_rate"], 1),
        "assign_submission_rate": round(global_features["assignment_submission_rate"], 1),
        "videos_completed":       global_features["videos_completed"],
        "quizzes_attempted":      global_features["quizzes_attempted"],
        "assignments_submitted":  global_features["assignments_submitted"],
        "level":          global_level,
        "dropout_risk":   global_risk,
        "enrolled_courses": courses_data,
        "video_progress": video_progress_data,
        "quiz_history":   quiz_history,
        "assign_history": assign_history
    }

@router.get("/students/{student_id}/quiz-attempts")
def get_student_quiz_attempts(
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    attempts = db.query(models.QuizAttempt).filter(models.QuizAttempt.student_id == student_id).all()
    result = []
    for a in attempts:
        q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == a.quiz_id).count()
        result.append({
            "quiz_id": a.quiz_id,
            "score": a.score,
            "percentage": round((a.score / q_count) * 100, 2) if q_count > 0 else 0
        })
    return result

@router.get("/students/{student_id}/assignment-submissions")
def get_student_submissions(
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    subs = db.query(models.AssignmentSubmission).filter(models.AssignmentSubmission.student_id == student_id).all()
    # We need to include total_marks for the teacher's UI to calculate percentages correctly
    result = []
    for s in subs:
        assignment = db.query(models.Assignment).filter(models.Assignment.id == s.assignment_id).first()
        total_m = assignment.total_marks if assignment else 10
        result.append({
            "id": s.id,
            "assignment_id": s.assignment_id,
            "assignment_title": assignment.title if assignment else "Unknown",
            "student_answer": s.student_answer,
            "obtained_marks": s.obtained_marks,
            "total_marks": total_m,
            "is_manual_review": s.is_manual_review,
            "submitted_at": s.submitted_at
        })
    return result

@router.get("/students/{student_id}/video-progress")
def get_student_video_progress(
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    records = db.query(models.VideoProgress).filter(models.VideoProgress.student_id == student_id).all()
    return [{
        "video_id": r.video_id,
        "watch_time": r.watch_time,
        "watch_percentage": r.watch_percentage
    } for r in records]

@router.get("/analytics")
def get_analytics(
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    org_id = teacher.organization_id
    
    # 1. Course Enrollment Distribution
    if course_id:
        topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).all()
        course_stats = []
        for t in topics:
            q_ids = [q[0] for q in db.query(models.Quiz.id).filter(models.Quiz.topic_id == t.id).all()]
            avg_q = db.query(func.avg(models.QuizAttempt.score)).filter(models.QuizAttempt.quiz_id.in_(q_ids)).scalar() or 0 if q_ids else 0
            course_stats.append({"title": t.title, "students": round(avg_q, 1)})
    else:
        courses = db.query(models.Course).filter(models.Course.organization_id == org_id).all()
        course_stats = []
        for c in courses:
            count = db.query(models.Enrollment).filter(models.Enrollment.course_id == c.id).count()
            course_stats.append({"title": c.title, "students": count})
    
    # 2. Learner Level Distribution (using actual stored levels)
    student_query = db.query(models.StudentPerformanceSummary.learner_level).join(
        models.User, models.StudentPerformanceSummary.student_id == models.User.id
    ).filter(models.User.organization_id == org_id)
    
    if course_id:
        student_query = student_query.join(models.Enrollment, models.User.id == models.Enrollment.student_id).filter(models.Enrollment.course_id == course_id)
    
    results = student_query.all()
    levels = {"Strong": 0, "Average": 0, "Weak": 0}
    for r in results:
        lvl = r[0]
        if lvl in levels:
            levels[lvl] += 1
        else:
            levels["Average"] += 1

    return {
        "course_distribution": course_stats,
        "level_distribution": levels,
        "total_courses": 1 if course_id else len(db.query(models.Course).filter(models.Course.organization_id == org_id).all()),
        "total_students": len(results)
    }


# ── TEACHER: Student Certificates ─────────────────────────────────────────────
@router.get("/students/{student_id}/certificates")
def get_student_certificates_for_teacher(
    student_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    """Return all certificate records for a student, filtered to this teacher's org."""
    student = db.query(models.User).filter(
        models.User.id == student_id,
        models.User.organization_id == teacher.organization_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    certs = db.query(models.Certificate, models.Course.title)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(models.Certificate.student_id == student_id)\
        .order_by(models.Certificate.request_date.desc())\
        .all()

    result = []
    for cert, course_title in certs:
        m, _, _ = get_student_metrics(db, student_id, cert.course_id)
        result.append({
            "id": cert.id,
            "course_title": course_title,
            "status": cert.status,
            "issued": cert.issued,
            "score": round(m["overall_score"], 1),
            "request_date": cert.request_date.isoformat() if cert.request_date else None,
            "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        })
    return result

# ── TEACHER: Certificate Requests (Global for Teacher's Org) ─────────────────
@router.get("/certificates/requests")
def get_teacher_pending_requests(
    teacher: models.User = Depends(get_current_teacher), 
    db: Session = Depends(get_db)
):
    reqs = db.query(models.Certificate, models.User.name, models.User.email, models.Course.title)\
        .join(models.User, models.Certificate.student_id == models.User.id)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(
            models.Course.organization_id == teacher.organization_id,
            models.Certificate.status == "pending"
        ).all()
    
    result = []
    for cert, name, email, title in reqs:
        m, l, r = get_student_metrics(db, cert.student_id, cert.course_id)
        result.append({
            "id": cert.id, 
            "student_name": name, 
            "student_email": email,
            "course_title": title, 
            "score": round(m["overall_score"]),
            "completion": round(m["completion_rate"]),
            "request_date": cert.request_date.isoformat() if cert.request_date else None
        })
    return result

@router.get("/certificates/issued")
def get_teacher_issued_certificates(
    teacher: models.User = Depends(get_current_teacher), 
    db: Session = Depends(get_db)
):
    issued = db.query(models.Certificate, models.User.name, models.User.email, models.Course.title)\
        .join(models.User, models.Certificate.student_id == models.User.id)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(
            models.Course.organization_id == teacher.organization_id,
            models.Certificate.issued == True
        ).all()
    
    return [{
        "id": c.id, 
        "student_name": name, 
        "student_email": email,
        "course_title": title,
        "issued_at": c.issued_at.isoformat() if c.issued_at else None
    } for c, name, email, title in issued]

@router.post("/certificates/{cert_id}/issue")
def issue_certificate_teacher(
    cert_id: int,
    teacher: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    cert = db.query(models.Certificate).join(models.Course).filter(
        models.Certificate.id == cert_id,
        models.Course.organization_id == teacher.organization_id
    ).first()
    
    if not cert:
        raise HTTPException(status_code=404, detail="Request not found")
        
    cert.status = "verified"
    cert.issued = True
    cert.issued_at = datetime.utcnow()
    db.commit()
    return {"message": "Certificate issued"}

@router.post("/certificates/{cert_id}/reject")
def reject_certificate_teacher(
    cert_id: int,
    teacher: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    cert = db.query(models.Certificate).join(models.Course).filter(
        models.Certificate.id == cert_id,
        models.Course.organization_id == teacher.organization_id
    ).first()
    
    if not cert:
        raise HTTPException(status_code=404, detail="Request not found")
        
    cert.status = "rejected"
    db.commit()
    return {"message": "Certificate rejected"}