from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func
from datetime import datetime, timedelta
import models, os, shutil, json
from dependencies import get_db, get_current_admin
# from routers.student import predict_learner_level  <-- Commented out to prevent circular import
from routers.dashboard import get_student_metrics
from auth import hash_password
from typing import List, Optional

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

# ── DASHBOARD ────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def admin_dashboard(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    org_id = admin.organization_id
    
    # All teachers in org
    teachers = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "teacher"
    ).all()
    
    # All courses in org
    courses = db.query(models.Course).filter(
        models.Course.organization_id == org_id
    ).all()
    course_ids = [c.id for c in courses]
    
    # All students in org
    students = db.query(models.User).filter(
        models.User.organization_id == org_id,
        models.User.role == "student"
    ).all()
    student_ids = [s.id for s in students]
    
    # Platform avg score from raw calculation
    total_score = 0
    student_count_with_perf = 0
    levels = {"Strong": 0, "Average": 0, "Weak": 0}
    
    for sid in student_ids:
        metrics, level, risk = get_student_metrics(db, sid)
        if metrics["overall_score"] > 0:
            total_score += metrics["overall_score"]
            student_count_with_perf += 1
        if level in levels:
            levels[level] += 1
            
    avg_score = round(total_score / student_count_with_perf, 1) if student_count_with_perf > 0 else 0
    
    # Certificates issued
    certs = db.query(models.Certificate).filter(
        models.Certificate.course_id.in_(course_ids),
        models.Certificate.issued == True
    ).count() if course_ids else 0
    
    # Active this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_week = db.query(models.VideoProgress).filter(
        models.VideoProgress.student_id.in_(student_ids)
    ).distinct(models.VideoProgress.student_id).count() if student_ids else 0
    
    # Course distribution
    course_dist = []
    for c in courses[:8]:
        enrolled = db.query(models.Enrollment).filter(
            models.Enrollment.course_id == c.id
        ).count()
        course_dist.append({"title": c.title[:20], "students": enrolled})
    
    # Teacher performance
    teacher_perf = []
    for t in teachers:
        t_courses = [c for c in courses if c.created_by == t.id]
        t_course_ids = [c.id for c in t_courses]
        
        t_total_score = 0
        t_student_count = 0
        t_enrollments = db.query(models.Enrollment.student_id).filter(models.Enrollment.course_id.in_(t_course_ids)).distinct().all() if t_course_ids else []
        for (sid,) in t_enrollments:
            m, l, r = get_student_metrics(db, sid, None) 
            t_total_score += m["overall_score"]
            t_student_count += 1
            
        t_avg = round(t_total_score / t_student_count, 1) if t_student_count > 0 else 0
        
        teacher_perf.append({
            "id": t.id, "name": t.name,
            "course_count": len(t_courses),
            "student_count": t_student_count,
            "avg_score": t_avg,
            "is_active": t.status
        })
    
    return {
        "total_teachers": len(teachers),
        "total_students": len(students),
        "total_courses": len(courses),
        "platform_avg_score": avg_score,
        "certificates_issued": certs,
        "active_this_week": active_week,
        "course_distribution": sorted(course_dist, key=lambda x: -x["students"]),
        "level_distribution": levels,
        "teacher_performance": teacher_perf
    }

# ── TEACHERS ─────────────────────────────────────────────────────────────────
@router.get("/teachers")
def get_teachers(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    teachers = db.query(models.User).filter(
        models.User.organization_id == admin.organization_id,
        models.User.role == "teacher"
    ).all()
    result = []
    for t in teachers:
        courses = db.query(models.Course).filter(models.Course.created_by == t.id).all()
        course_ids = [c.id for c in courses]
        
        t_total_score = 0
        t_student_count = 0
        t_enrollments = db.query(models.Enrollment.student_id).filter(models.Enrollment.course_id.in_(course_ids)).distinct().all() if course_ids else []
        for (sid,) in t_enrollments:
            m, l, r = get_student_metrics(db, sid)
            t_total_score += m["overall_score"]
            t_student_count += 1
            
        avg = round(t_total_score / t_student_count, 1) if t_student_count > 0 else 0
        
        result.append({
            "id": t.id, "name": t.name, "email": t.email,
            "is_active": t.status,
            "course_count": len(courses),
            "student_count": t_student_count,
            "avg_score": avg,
            "created_at": t.created_at.isoformat() if t.created_at else None
        })
    return result

@router.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    teacher = db.query(models.User).filter(
        models.User.id == teacher_id,
        models.User.organization_id == admin.organization_id,
        models.User.role == "teacher"
    ).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    db.delete(teacher)
    db.commit()
    return {"message": "Teacher deleted successfully"}

@router.get("/teachers/{teacher_id}/detail")
def get_teacher_detail(
    teacher_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)
):
    teacher = db.query(models.User).filter(
        models.User.id == teacher_id,
        models.User.organization_id == admin.organization_id
    ).first()
    if not teacher: raise HTTPException(status_code=404, detail="Teacher not found")
    
    courses = db.query(models.Course).filter(models.Course.created_by == teacher_id).all()
    course_ids = [c.id for c in courses]
    
    t_total_score = 0
    t_student_count = 0
    t_enrollments_distinct = db.query(models.Enrollment.student_id).filter(models.Enrollment.course_id.in_(course_ids)).distinct().all() if course_ids else []
    for (sid,) in t_enrollments_distinct:
        m, l, r = get_student_metrics(db, sid)
        t_total_score += m["overall_score"]
        t_student_count += 1
            
    avg = round(t_total_score / t_student_count, 1) if t_student_count > 0 else 0
    
    doubts_answered = db.query(models.ChatDoubt).filter(
        models.ChatDoubt.faculty_id == teacher_id,
        models.ChatDoubt.response != None
    ).count()
    
    courses_data = []
    for c in courses:
        enrolled = db.query(models.Enrollment).filter(models.Enrollment.course_id == c.id).count()
        c_score_sum = 0
        c_students = db.query(models.Enrollment.student_id).filter(models.Enrollment.course_id == c.id).all()
        for (sid,) in c_students:
            cm, cl, cr = get_student_metrics(db, sid, c.id)
            c_score_sum += cm["overall_score"]
        c_avg = round(c_score_sum / enrolled, 1) if enrolled > 0 else 0
        
        courses_data.append({
            "id": c.id, "title": c.title, "enrolled": enrolled,
            "avg_score": c_avg, "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
        
    return {
        "profile": {
            "id": teacher.id, "name": teacher.name, "email": teacher.email,
            "is_active": teacher.status,
            "created_at": teacher.created_at.isoformat() if teacher.created_at else None
        },
        "stats": {
            "course_count": len(courses), "student_count": t_student_count,
            "avg_score": avg, "doubts_answered": doubts_answered
        },
        "courses": courses_data
    }

# ── ADMIN COURSES ─────────────────────────────────────────────────────────────
@router.get("/courses")
def get_all_courses(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    courses = db.query(models.Course).filter(models.Course.organization_id == admin.organization_id).all()
    result = []
    for c in courses:
        teacher = db.query(models.User).filter(models.User.id == c.created_by).first()
        enrolled = db.query(models.Enrollment).filter(models.Enrollment.course_id == c.id).count()
        result.append({
            "id": c.id, "title": c.title, "description": c.description,
            "difficulty": c.difficulty, "logo": c.logo, "status": c.status,
            "teacher_name": teacher.name if teacher else "Unassigned",
            "teacher_id": c.created_by, "enrolled_students": enrolled
        })
    return result

@router.put("/courses/{course_id}/status")
def toggle_course_status(course_id: int, status: bool = Form(...), admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.organization_id == admin.organization_id).first()
    if not course: raise HTTPException(status_code=404, detail="Course not found")
    course.status = status
    db.commit()
    return {"message": "Course status updated"}

@router.delete("/courses/{course_id}")
def delete_course(course_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.organization_id == admin.organization_id).first()
    if not course: raise HTTPException(status_code=404, detail="Course not found")
    db.delete(course)
    db.commit()
    return {"message": "Course deleted"}

from routers.notifications import create_notification

@router.put("/courses/{course_id}/assign")
def assign_course_to_teacher(course_id: int, teacher_id: int = Form(...), admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.organization_id == admin.organization_id).first()
    if not course: raise HTTPException(status_code=404, detail="Course not found")
    teacher = db.query(models.User).filter(models.User.id == teacher_id, models.User.organization_id == admin.organization_id, models.User.role == "teacher").first()
    if not teacher: raise HTTPException(status_code=400, detail="Invalid teacher")
    course.created_by = teacher_id
    db.commit()

    # Notify Teacher
    create_notification(
        db, teacher_id, 
        "New Course Assigned", 
        f"The administrator has assigned you to the course: {course.title}",
        "courses.html"
    )

    return {"message": f"Course assigned to {teacher.name}"}

@router.get("/courses/{course_id}")
def get_admin_course_detail(course_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id, models.Course.organization_id == admin.organization_id).first()
    if not course: raise HTTPException(status_code=404, detail="Course not found")
    
    topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).order_by(models.Topic.order_number).all()
    topics_data = []
    for t in topics:
        topics_data.append({
            "id": t.id, "title": t.title,
            "videos": db.query(models.Video).filter(models.Video.topic_id == t.id).all(),
            "quizzes": db.query(models.Quiz).filter(models.Quiz.topic_id == t.id).all(),
            "assignments": db.query(models.Assignment).filter(models.Assignment.topic_id == t.id).all()
        })
    
    return {
        "id": course.id, "title": course.title, "description": course.description,
        "difficulty": course.difficulty, "logo": course.logo, "status": course.status,
        "topics": topics_data
    }

@router.get("/courses/{course_id}/topics")
def get_admin_course_topics(course_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.Topic).filter(models.Topic.course_id == course_id).all()

# ── ADMIN STUDENTS ────────────────────────────────────────────────────────────
from fastapi.responses import StreamingResponse
import io, pandas as pd

@router.post("/bulk-import")
async def bulk_import_users(
    file: UploadFile = File(...),
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed.")
    
    try:
        if ext == ".csv":
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    
    required_cols = ["name", "email", "role"]
    if not all(col in df.columns for col in required_cols):
        raise HTTPException(status_code=400, detail=f"File must contain columns: {', '.join(required_cols)}")
    
    TEACHER_PWD_HASH = hash_password("Teacher@123")
    STUDENT_PWD_HASH = hash_password("Student@123")
    
    summary = {"total_processed": 0, "created": 0, "errors": []}
    
    for index, row in df.iterrows():
        summary["total_processed"] += 1
        
        if pd.isna(row.get("name")) or pd.isna(row.get("email")) or pd.isna(row.get("role")):
            summary["errors"].append({"email": str(row.get("email", "Unknown")), "error": "Missing required data (name, email, or role)"})
            continue

        name = str(row["name"]).strip()
        email = str(row["email"]).strip()
        role = str(row["role"]).strip().lower()
        
        if not name or not email or not role:
            summary["errors"].append({"email": email, "error": "Empty values not allowed"})
            continue
            
        if role not in ["teacher", "student"]:
            summary["errors"].append({"email": email, "error": f"Invalid role: {role}"})
            continue
            
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            summary["errors"].append({"email": email, "error": "Email already registered"})
            continue
            
        try:
            pwd_hash = TEACHER_PWD_HASH if role == "teacher" else STUDENT_PWD_HASH
            new_user = models.User(
                name=name,
                email=email,
                password_hash=pwd_hash,
                role=role,
                organization_id=admin.organization_id,
                status=True
            )
            db.add(new_user)
            summary["created"] += 1
        except Exception as e:
            summary["errors"].append({"email": email, "error": str(e)})
            
    db.commit()
    return summary

@router.get("/students")
def get_all_students(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    students = db.query(models.User).filter(
        models.User.organization_id == admin.organization_id,
        models.User.role == "student"
    ).order_by(models.User.created_at.desc()).all()
    result = []
    for s in students:
        metrics, level, risk = get_student_metrics(db, s.id)
        enrollments = (
            db.query(models.Enrollment, models.Course.title)
            .join(models.Course)
            .filter(models.Enrollment.student_id == s.id)
            .order_by(models.Enrollment.enrolled_at.desc())
            .all()
        )
        issued_certs = db.query(models.Certificate).filter(
            models.Certificate.student_id == s.id,
            models.Certificate.issued == True
        ).count()
        result.append({
            "id":            s.id,
            "name":          s.name,
            "email":         s.email,
            "is_active":     s.status,
            "overall_score": round(metrics["overall_score"], 1),
            "learner_level": level,
            "dropout_risk":  risk,
            "course_count":  len(enrollments),
            "certs_issued":  issued_certs,
            "main_course":   enrollments[0][1] if enrollments else "—",
            "joined":        s.created_at.strftime("%b %d, %Y") if s.created_at else "—",
        })
    return result

@router.get("/students/{student_id}/quiz-attempts")
def get_admin_student_quiz_attempts(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    attempts = db.query(models.QuizAttempt).filter(models.QuizAttempt.student_id == student_id).all()
    result = []
    for a in attempts:
        q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == a.quiz_id).count()
        result.append({
            "quiz_id": a.quiz_id, "score": a.score,
            "percentage": round((a.score / q_count) * 100, 2) if q_count > 0 else 0
        })
    return result

@router.get("/students/{student_id}/assignment-submissions")
def get_admin_student_submissions(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    subs = db.query(models.AssignmentSubmission).filter(models.AssignmentSubmission.student_id == student_id).all()
    result = []
    for s in subs:
        total_m = db.query(models.Assignment.total_marks).filter(models.Assignment.id == s.assignment_id).scalar() or 10
        result.append({
            "assignment_id": s.assignment_id, "obtained_marks": s.obtained_marks, "total_marks": total_m
        })
    return result

@router.get("/students/{student_id}/video-progress")
def get_admin_student_video_progress(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    records = db.query(models.VideoProgress).filter(models.VideoProgress.student_id == student_id).all()
    return [{"video_id": r.video_id, "watch_time": r.watch_time, "watch_percentage": r.watch_percentage} for r in records]

@router.get("/students/{student_id}/enrollments")
def get_admin_student_enrollments(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.student_id == student_id).all()
    return [{"course_id": e.course_id, "enrolled_at": e.enrolled_at} for e in enrollments]

@router.get("/students/export")
def export_all_students_excel(
    token: str = None,
    admin=Depends(get_current_admin), db: Session = Depends(get_db)
):
    data = get_all_students(admin, db)
    if not data:
        raise HTTPException(status_code=400, detail="No data")

    org = db.query(models.Organization).filter(
        models.Organization.id == admin.organization_id
    ).first()
    org_name = (org.platform_name or org.name) if org else "LearnHub"

    from excel_export import build_admin_report
    buf = build_admin_report(
        students=data,
        org_name=org_name,
        db=db,
        get_student_metrics=get_student_metrics,
        models=models
    )

    safe_org = "".join(c for c in org_name.replace(" ", "_") if ord(c) < 128) or "Org"
    filename = f"Platform_Students_{safe_org}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    headers  = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, headers=headers,
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/students/{student_id}/detail")
def get_admin_student_detail(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(
        models.User.id == student_id,
        models.User.organization_id == admin.organization_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    global_metrics, global_level, global_risk = get_student_metrics(db, student_id)

    enrollments = db.query(models.Enrollment).filter(
        models.Enrollment.student_id == student_id
    ).order_by(models.Enrollment.enrolled_at).all()

    courses_data = []
    for enr in enrollments:
        course = db.query(models.Course).filter(models.Course.id == enr.course_id).first()
        if not course:
            continue
        c_metrics, c_level, c_risk = get_student_metrics(db, student_id, course.id)
        topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course.id).all()]
        total_vids    = db.query(models.Video).filter(models.Video.topic_id.in_(topic_ids)).count() if topic_ids else 0
        total_quizzes = db.query(models.Quiz).filter(models.Quiz.topic_id.in_(topic_ids)).count() if topic_ids else 0
        total_assigns = db.query(models.Assignment).filter(models.Assignment.topic_id.in_(topic_ids)).count() if topic_ids else 0
        courses_data.append({
            "id":             course.id,
            "title":          course.title,
            "enrolled_at":    enr.enrolled_at.strftime("%b %d, %Y") if enr.enrolled_at else "—",
            "overall":        round(c_metrics["overall_score"], 1),
            "quiz_avg":       round(c_metrics["quiz_average"], 1),
            "assign_avg":     round(c_metrics["assignment_average"], 1),
            "completion_rate":round(c_metrics["completion_rate"], 1),
            "videos":         f"{c_metrics['videos_completed']}/{total_vids}",
            "quizzes":        f"{c_metrics['quizzes_attempted']}/{total_quizzes}",
            "assignments":    f"{c_metrics['assignments_submitted']}/{total_assigns}",
            "level":          c_level,
            "risk":           c_risk,
        })

    recent_attempts = (
        db.query(models.QuizAttempt, models.Quiz.title, models.Course.title.label("course"))
        .join(models.Quiz,   models.QuizAttempt.quiz_id   == models.Quiz.id)
        .join(models.Topic,  models.Quiz.topic_id          == models.Topic.id)
        .join(models.Course, models.Topic.course_id        == models.Course.id)
        .filter(models.QuizAttempt.student_id == student_id)
        .order_by(models.QuizAttempt.attempted_at.desc())
        .limit(8).all()
    )
    quiz_history = []
    for att, q_title, c_title in recent_attempts:
        q_count = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == att.quiz_id).count()
        pct = round((att.score / q_count) * 100) if q_count > 0 else 0
        quiz_history.append({
            "quiz":   q_title,
            "course": c_title,
            "score":  f"{att.score}/{q_count}",
            "pct":    pct,
            "date":   att.attempted_at.strftime("%b %d, %Y") if att.attempted_at else "—",
        })

    recent_subs = (
        db.query(models.AssignmentSubmission, models.Assignment.title,
                 models.Assignment.total_marks, models.Course.title.label("course"))
        .join(models.Assignment, models.AssignmentSubmission.assignment_id == models.Assignment.id)
        .join(models.Topic,      models.Assignment.topic_id                == models.Topic.id)
        .join(models.Course,     models.Topic.course_id                    == models.Course.id)
        .filter(models.AssignmentSubmission.student_id == student_id)
        .order_by(models.AssignmentSubmission.submitted_at.desc())
        .limit(8).all()
    )
    assign_history = []
    for sub, a_title, t_marks, c_title in recent_subs:
        pct = round((sub.obtained_marks / t_marks) * 100) if t_marks and t_marks > 0 else 0
        assign_history.append({
            "title":  a_title,
            "course": c_title,
            "score":  f"{sub.obtained_marks}/{t_marks}",
            "pct":    pct,
            "date":   sub.submitted_at.strftime("%b %d, %Y") if sub.submitted_at else "—",
        })

    joined = student.created_at.strftime("%B %d, %Y") if student.created_at else "—"

    return {
        "id":             student.id,
        "name":           student.name,
        "email":          student.email,
        "joined":         joined,
        "is_active":      student.status,
        "learner_level":  global_level,
        "dropout_risk":   global_risk,
        "overall_score":  round(global_metrics["overall_score"], 1),
        "quiz_average":   round(global_metrics["quiz_average"], 1),
        "assign_average": round(global_metrics["assignment_average"], 1),
        "completion_rate":round(global_metrics["completion_rate"], 1),
        "quiz_attempt_rate":      round(global_metrics["quiz_attempt_rate"], 1),
        "assign_submission_rate": round(global_metrics["assignment_submission_rate"], 1),
        "videos_completed":       global_metrics["videos_completed"],
        "quizzes_attempted":      global_metrics["quizzes_attempted"],
        "assignments_submitted":  global_metrics["assignments_submitted"],
        "enrolled_count":  len(enrollments),
        "enrolled_courses": courses_data,
        "quiz_history":    quiz_history,
        "assign_history":  assign_history,
    }

# ── ADMIN CERTIFICATES ────────────────────────────────────────────────────────
@router.get("/certificates/requests")
def get_pending_requests(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    reqs = db.query(models.Certificate, models.User.name, models.User.email, models.Course.title)\
        .join(models.User, models.Certificate.student_id == models.User.id)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(models.Certificate.status == "pending")\
        .all()
    
    result = []
    for cert, name, email, title in reqs:
        m, l, r = get_student_metrics(db, cert.student_id, cert.course_id)
        result.append({
            "id": cert.id, "student_name": name, "student_email": email,
            "course_title": title, "score": round(m["overall_score"]),
            "request_date": cert.request_date.isoformat() if cert.request_date else None
        })
    return result

@router.get("/certificates/issued")
def get_issued_certificates(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    Student = aliased(models.User)
    Teacher = aliased(models.User)
    
    issued = db.query(
        models.Certificate, 
        Student.name.label("student_name"), 
        models.Course.title, 
        Teacher.name.label("teacher_name")
    )\
    .join(Student, models.Certificate.student_id == Student.id)\
    .join(models.Course, models.Certificate.course_id == models.Course.id)\
    .join(Teacher, models.Course.created_by == Teacher.id)\
    .filter(models.Certificate.issued == True)\
    .all()
    
    return [{
        "id": c.id, "student_name": student_name, "course_title": title,
        "teacher_name": teacher_name,
        "issued_at": c.issued_at.isoformat() if c.issued_at else None
    } for c, student_name, title, teacher_name in issued]

@router.get("/certificates/{cert_id}/download")
def admin_download_certificate(cert_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    cert = db.query(models.Certificate).filter(
        models.Certificate.id     == cert_id,
        models.Certificate.issued == True
    ).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found or not yet issued.")

    student = db.query(models.User).filter(models.User.id == cert.student_id).first()
    course  = db.query(models.Course).filter(models.Course.id == cert.course_id).first()
    org     = db.query(models.Organization).filter(models.Organization.id == admin.organization_id).first()

    from certificate_generator import generate_certificate_pdf
    from fastapi.responses import StreamingResponse

    pdf_buffer = generate_certificate_pdf(
        student_name=student.name,
        course_name=course.title,
        org_name=(org.platform_name or org.name) if org else "LearnHub",
        logo_url=org.logo if org else None,
        signature_url=org.signature_url if org else None,
        issue_date=cert.issued_at.strftime("%B %d, %Y") if cert.issued_at else None
    )
    def _safe(s):
        return "".join(ch for ch in s.replace(" ", "_") if ord(ch) < 128 and ch not in r'\/:*?"<>|') or "file"

    headers = {
        'Content-Disposition':
            f'inline; filename="Certificate_{_safe(student.name)}_{_safe(course.title)}.pdf"'
    }
    return StreamingResponse(pdf_buffer, headers=headers, media_type='application/pdf')

@router.get("/students/{student_id}/certificates")
def get_admin_student_certificates(student_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    student = db.query(models.User).filter(
        models.User.id == student_id,
        models.User.organization_id == admin.organization_id
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

# ── ADMIN ANALYTICS ───────────────────────────────────────────────────────────
@router.get("/analytics")
def get_admin_analytics(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    org_id = admin.organization_id
    courses = db.query(models.Course).filter(models.Course.organization_id == org_id).all()
    students = db.query(models.User).filter(models.User.organization_id == org_id, models.User.role == "student").all()
    student_ids = [s.id for s in students]
    
    total_score = 0
    total_comp_rate = 0
    levels = {"Strong": 0, "Average": 0, "Weak": 0}
    
    for sid in student_ids:
        metrics, level, risk = get_student_metrics(db, sid)
        total_score += metrics["overall_score"]
        total_comp_rate += metrics["completion_rate"]
        if level in levels: levels[level] += 1
            
    n = len(student_ids) or 1
    platform_avg = round(total_score / n, 1)
    completion_avg = round(total_comp_rate / n, 1)
    
    # Monthly growth
    monthly = []
    for i in range(5, -1, -1):
        month_start = (datetime.utcnow().replace(day=1) - timedelta(days=i*30))
        month_end   = month_start + timedelta(days=30)
        count = db.query(models.User).filter(models.User.organization_id == org_id, models.User.role == "student", models.User.created_at >= month_start, models.User.created_at < month_end).count()
        monthly.append({"month": month_start.strftime("%b %Y"), "count": count})
    
    # Course performance
    course_perf = []
    for c in courses:
        enrollments = db.query(models.Enrollment.student_id).filter(models.Enrollment.course_id == c.id).all()
        c_score_sum = 0
        for (sid,) in enrollments:
            m, l, r = get_student_metrics(db, sid, c.id)
            c_score_sum += m["overall_score"]
        c_avg = round(c_score_sum / len(enrollments), 1) if enrollments else 0
        teacher = db.query(models.User).filter(models.User.id == c.created_by).first()
        course_perf.append({"title": c.title, "avg_score": c_avg, "teacher_name": teacher.name if teacher else "—"})
    
    # ML Dropout Risk Distribution
    risk_dist = {"Low": 0, "Medium": 0, "High": 0}
    perf_summaries = db.query(models.StudentPerformanceSummary).filter(models.StudentPerformanceSummary.student_id.in_(student_ids)).all()
    for ps in perf_summaries:
        if ps.dropout_risk in risk_dist:
            risk_dist[ps.dropout_risk] += 1
    
    # AI vs Faculty Doubt Stats
    doubt_stats = {
        "ai_count": db.query(models.ChatDoubt).filter(models.ChatDoubt.student_id.in_(student_ids), models.ChatDoubt.mode == "AI").count(),
        "faculty_count": db.query(models.ChatDoubt).filter(models.ChatDoubt.student_id.in_(student_ids), models.ChatDoubt.mode == "FACULTY").count()
    }

    # Course Drop-off Analysis
    dropoff_data = []
    all_topics = db.query(models.Topic).join(models.Course).filter(models.Course.organization_id == org_id).all()
    for t in all_topics:
        total_enrolled = db.query(models.Enrollment).filter(models.Enrollment.course_id == t.course_id).count()
        if total_enrolled > 0:
            completed_count = db.query(models.TopicProgress).filter(models.TopicProgress.topic_id == t.id, models.TopicProgress.completed == True).count()
            completion_pct = (completed_count / total_enrolled) * 100
            if completion_pct < 100:
                dropoff_data.append({"topic": t.title, "course": db.query(models.Course.title).filter(models.Course.id == t.course_id).scalar(), "completion": round(completion_pct, 1)})
    
    top_dropoffs = sorted(dropoff_data, key=lambda x: x["completion"])[:5]

    # Simple Engagement Rates
    v_comp_total = sum([get_student_metrics(db, sid)[0]["completion_rate"] for sid in student_ids]) if student_ids else 0
    q_att_total = sum([get_student_metrics(db, sid)[0]["quiz_attempt_rate"] for sid in student_ids]) if student_ids else 0
    a_sub_total = sum([get_student_metrics(db, sid)[0]["assignment_submission_rate"] for sid in student_ids]) if student_ids else 0

    return {
        "total_students": len(student_ids), "total_courses": len(courses),
        "platform_avg_score": platform_avg, "completion_rate": completion_avg,
        "monthly_growth": monthly, "course_performance": sorted(course_perf, key=lambda x: -x["avg_score"]),
        "level_distribution": levels,
        "risk_distribution": risk_dist,
        "doubt_stats": doubt_stats,
        "top_dropoffs": top_dropoffs,
        "engagement": {
            "video_rate": round(v_comp_total / n),
            "quiz_rate": round(q_att_total / n),
            "assign_rate": round(a_sub_total / n)
        }
    }

@router.post("/teachers/invite")
def invite_teacher(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_teacher = models.User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role="teacher",
        organization_id=admin.organization_id,
        status=True
    )
    db.add(new_teacher)
    db.commit()
    db.refresh(new_teacher)
    return {"message": "Teacher account created successfully", "id": new_teacher.id}

# ── ADMIN ORGANIZATION & PROFILE ──────────────────────────────────────────────
def get_full_url(path: str):
    if not path: return None
    if path.startswith("http"): return path
    return f"http://127.0.0.1:8000/{path}"

@router.get("/organization")
def get_organization(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.id == admin.organization_id).first()
    if not org: raise HTTPException(status_code=404, detail="Not found")
    return {
        "org_name": org.name, 
        "platform_name": org.platform_name, 
        "logo": get_full_url(org.logo),
        "signature": get_full_url(org.signature_url)
    }

from cloudinary_utils import upload_to_cloudinary

@router.put("/organization")
async def update_organization(
    org_name: str = Form(None),
    platform_name: str = Form(None),
    logo: UploadFile = File(None),
    signature: UploadFile = File(None),
    admin=Depends(get_current_admin), db: Session = Depends(get_db)
):
    org = db.query(models.Organization).filter(
        models.Organization.id == admin.organization_id
    ).first()
    if not org: raise HTTPException(status_code=404, detail="Organization not found")

    if org_name: org.name = org_name
    if platform_name: org.platform_name = platform_name

    if logo and logo.filename:
        cloud_url = upload_to_cloudinary(logo, folder="learnhub/logos")
        if cloud_url:
            org.logo = cloud_url

    if signature and signature.filename:
        sig_url = upload_to_cloudinary(signature, folder="learnhub/signatures")
        if sig_url:
            org.signature_url = sig_url

    db.commit()
    db.refresh(org)
    return {
        "org_name": org.name,
        "platform_name": org.platform_name,
        "logo": get_full_url(org.logo),
        "signature": get_full_url(org.signature_url)
    }

@router.get("/profile")
def get_admin_profile(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    return {"id": admin.id, "name": admin.name, "email": admin.email}

@router.put("/profile")
def update_admin_profile(name: str = Form(None), email: str = Form(None), current_password: str = Form(None), new_password: str = Form(None), admin_user=Depends(get_current_admin), db: Session = Depends(get_db)):
    from auth import verify_password, hash_password
    if name: admin_user.name = name
    if email: admin_user.email = email
    if current_password and new_password:
        if not verify_password(current_password, admin_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        admin_user.password_hash = hash_password(new_password)
    db.commit()
    return {"message": "Profile updated"}
