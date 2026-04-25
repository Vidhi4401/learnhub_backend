from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas, shutil, os, io, json
from datetime import datetime
from dependencies import get_current_teacher
from groq import Groq
from config import GROQ_API_KEY
import PyPDF2
from sqlalchemy import text
router = APIRouter(prefix="/api/v1/teacher", tags=["Teacher Courses"])

client = Groq(api_key=GROQ_API_KEY.strip() if GROQ_API_KEY else "")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/courses/{course_id}/process-pdf-preview")
async def process_course_pdf_preview(
    course_id: int,
    file: UploadFile = File(...),
    teacher: models.User = Depends(get_current_teacher)
):
    """
    Extracts text and returns AI-generated topics/quizzes/assignments for preview.
    Does NOT save to DB yet.
    """
    # 2. Extract text from PDF
    try:
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        extracted_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF. It might be scanned or empty.")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF error: {str(e)}")

    # 3. Use AI to structure the content
    prompt = f"""
    You are an expert curriculum designer. Analyze the provided text and extract a structured course curriculum.
    The text is from a course document. Extract multiple topics (aim for 3-5).

    For EACH topic identified:
    1. Provide a 'topic_name'.
    2. Create ONE 'assignment' with a 'title' and a detailed 'description' (at least 2 sentences).
    3. Create ONE 'quiz' with a 'title' and EXACTLY 5 Multiple Choice Questions (MCQs).
    4. Each 'question' must have: 'text', 'a', 'b', 'c', 'd', and the 'correct_answer' (must be one of "A", "B", "C", or "D").

    Text to analyze (truncated):
    {extracted_text[:12000]}

    Return ONLY a valid JSON object with a "topics" key.
    Format:
    {{
      "topics": [
        {{
          "topic_name": "...",
          "assignment": {{ "title": "...", "description": "..." }},
          "quiz": {{
            "title": "...",
            "questions": [
              {{ "text": "...", "a": "...", "b": "...", "c": "...", "d": "...", "correct_answer": "A" }},
              ... (total 5)
            ]
          }}
        }}
      ]
    }}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        data = json.loads(chat_completion.choices[0].message.content)
        return data
    except Exception as e:
        print(f"[AI Error] {str(e)}")
        raise HTTPException(status_code=500, detail="AI generation failed. Please try a different PDF.")

@router.post("/courses/generate-from-pdf")
async def generate_from_pdf(
    course_id: int = Form(...),
    file: UploadFile = File(...),
    teacher: models.User = Depends(get_current_teacher)
):
    """
    Extracts text and returns AI-generated topics/quizzes/assignments for preview.
    Matches frontend expectation where course_id is in Form data.
    """
    try:
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        extracted_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"

        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF. It might be scanned or empty.")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF error: {str(e)}")

    prompt = f"""
    You are an expert curriculum designer. Analyze the provided text and extract a structured course curriculum.
    The text is from a course document. Extract multiple topics (aim for 3-5).

    For EACH topic identified:
    1. Provide a 'topic_name'.
    2. Create ONE 'assignment' with a 'title' and a detailed 'description' (at least 2 sentences).
    3. Create ONE 'quiz' with a 'title' and EXACTLY 5 Multiple Choice Questions (MCQs).
    4. Each 'question' must have: 'text', 'a', 'b', 'c', 'd', and the 'correct_answer' (must be one of "A", "B", "C", or "D").

    Text to analyze (truncated):
    {extracted_text[:12000]}

    Return ONLY a valid JSON object with a "topics" key.
    Format:
    {{
      "topics": [
        {{
          "topic_name": "...",
          "assignment": {{ "title": "...", "description": "..." }},
          "quiz": {{
            "title": "...",
            "questions": [
              {{ "text": "...", "a": "...", "b": "...", "c": "...", "d": "...", "correct_answer": "A" }},
              ... (total 5)
            ]
          }}
        }}
      ]
    }}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        data = json.loads(chat_completion.choices[0].message.content)
        # Return course_id so the frontend can send it back in save-generated
        return {"course_id": course_id, "topics": data["topics"]}
    except Exception as e:
        print(f"[AI Error] {str(e)}")
        raise HTTPException(status_code=500, detail="AI generation failed. Please try a different PDF.")

@router.post("/courses/{course_id}/generate-ai-content")
async def generate_course_content_ai(
    course_id: int,
    teacher: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    Generates a full course curriculum (topics, quizzes, assignments) 
    based only on the course title and difficulty.
    """
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    prompt = f"""
    You are an expert curriculum designer. Create a comprehensive and structured course curriculum for:
    Course Title: "{course.title}"
    Difficulty Level: {course.difficulty}

    Requirements:
    1. Extract EXACTLY 5 high-quality topics that cover the subject thoroughly.
    2. For EACH topic:
       - Provide a 'topic_name'.
       - Create ONE 'assignment' with a 'title' and a detailed 'description' (at least 2 sentences).
       - Create ONE 'quiz' with a 'title' and EXACTLY 5 Multiple Choice Questions (MCQs).
       - Each 'question' must have: 'text', 'a', 'b', 'c', 'd', and the 'correct_answer' (must be one of "A", "B", "C", or "D").

    Return ONLY a valid JSON object with a "topics" key.
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        data = json.loads(chat_completion.choices[0].message.content)
        return data
    except Exception as e:
        print(f"[AI Content Generation Error] {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate AI content. Please try again.")

from routers.notifications import create_notification

@router.post("/courses/{course_id}/save-pdf-content")
def save_pdf_content(
    course_id: int,
    data: dict, # The JSON generated by AI and reviewed by teacher
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    """
    Saves the reviewed AI-generated content to the database.
    """
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == teacher.organization_id
    ).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    topics_data = data.get("topics", [])
    new_topics_count = 0
    try:
        current_topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).count()

        for idx, t_data in enumerate(topics_data):
            topic = models.Topic(
                title=t_data["topic_name"],
                course_id=course_id,
                order_number=current_topics + idx + 1
            )
            db.add(topic)
            db.flush()

            a_data = t_data.get("assignment")
            if a_data:
                db.add(models.Assignment(
                    topic_id=topic.id,
                    title=a_data["title"],
                    description=a_data["description"],
                    total_marks=10
                ))

            q_data = t_data.get("quiz")
            if q_data:
                quiz = models.Quiz(topic_id=topic.id, title=q_data["title"])
                db.add(quiz)
                db.flush()

                for qst in q_data.get("questions", []):
                    db.add(models.QuizQuestion(
                        quiz_id=quiz.id,
                        question_text=qst["text"],
                        option_a=qst["a"],
                        option_b=qst["b"],
                        option_c=qst["c"],
                        option_d=qst["d"],
                        correct_option=qst["correct_answer"]
                    ))
            new_topics_count += 1

        db.commit()
        
        # Notify all enrolled students about new content
        enrolled_students = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == course_id
        ).all()
        
        for (sid,) in enrolled_students:
            create_notification(
                db, sid,
                "New Course Content",
                f"New topics and assessments have been added to {course.title}.",
                "student-course-detail.html?id=" + str(course_id)
            )

        return {"message": f"Successfully saved {new_topics_count} topics."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

@router.post("/courses/save-generated")
def save_generated_content(
    data: dict,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    """
    Saves the AI-generated content. Expects {"course_id": int, "topics": [...]}
    Matches frontend expectation where all data is in the JSON body.
    """
    course_id = data.get("course_id")
    if not course_id:
        raise HTTPException(status_code=400, detail="course_id is required")

    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == teacher.organization_id
    ).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    topics_data = data.get("topics", [])
    new_topics_count = 0
    try:
        current_topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).count()

        for idx, t_data in enumerate(topics_data):
            topic = models.Topic(
                title=t_data["topic_name"],
                course_id=course_id,
                order_number=current_topics + idx + 1
            )
            db.add(topic)
            db.flush()

            a_data = t_data.get("assignment")
            if a_data:
                db.add(models.Assignment(
                    topic_id=topic.id,
                    title=a_data["title"],
                    description=a_data["description"],
                    total_marks=10
                ))

            q_data = t_data.get("quiz")
            if q_data:
                quiz = models.Quiz(topic_id=topic.id, title=q_data["title"])
                db.add(quiz)
                db.flush()

                for qst in q_data.get("questions", []):
                    db.add(models.QuizQuestion(
                        quiz_id=quiz.id,
                        question_text=qst["text"],
                        option_a=qst["a"],
                        option_b=qst["b"],
                        option_c=qst["c"],
                        option_d=qst["d"],
                        correct_option=qst["correct_answer"]
                    ))
            new_topics_count += 1

        db.commit()
        
        # Notify all enrolled students
        enrolled_students = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == course_id
        ).all()
        
        for (sid,) in enrolled_students:
            create_notification(
                db, sid,
                "New Course Content",
                f"New topics and assessments have been added to {course.title}.",
                "student-course-detail.html?id=" + str(course_id)
            )

        return {"message": f"Successfully saved {new_topics_count} topics."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


from cloudinary_utils import upload_to_cloudinary

@router.post("/courses")
def create_course(
    title: str = Form(...),
    description: str = Form(...),
    difficulty: str = Form(...),
    status: bool = Form(...),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    cloud_url = None
    if logo and logo.filename:
        cloud_url = upload_to_cloudinary(logo, folder="learnhub/courses")

    existing = db.query(models.Course).filter(
        models.Course.title == title,
        models.Course.organization_id == teacher.organization_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Course already exists")

    course = models.Course(
        title=title,
        description=description,
        difficulty=difficulty,
        status=status,
        logo=cloud_url,
        organization_id=teacher.organization_id,
        created_by=teacher.id
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"course_id": course.id}


@router.get("/courses")
def get_courses(
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    # Only show courses created by or assigned to this teacher
    return db.query(models.Course).filter(
        models.Course.organization_id == teacher.organization_id,
        models.Course.created_by == teacher.id
    ).all()

@router.get("/courses/organization")
def get_org_courses(
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    # View-only: all courses in the organization
    courses = db.query(models.Course).filter(
        models.Course.organization_id == teacher.organization_id
    ).all()
    
    result = []
    for c in courses:
        creator = db.query(models.User).filter(models.User.id == c.created_by).first()
        result.append({
            "id": c.id, "title": c.title, "logo": c.logo, 
            "teacher_name": creator.name if creator else "Admin",
            "created_by": c.created_by
        })
    return result


@router.get("/courses/{course_id}")
def get_single_course(course_id: int, db: Session = Depends(get_db)):
    return db.query(models.Course).filter(
        models.Course.id == course_id
    ).first()


@router.put("/courses/{course_id}")
def update_course(
    course_id: int,
    data: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id
    ).first()
    course.title       = data.title
    course.description = data.description
    course.difficulty  = data.difficulty
    course.status      = data.status
    db.commit()
    return {"message": "Course updated"}


@router.delete("/courses/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.created_by == teacher.id
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # ── Get all IDs needed for cascade delete ─────────────────────────────
    topic_ids = [t.id for t in db.query(models.Topic.id).filter(
        models.Topic.course_id == course_id).all()]

    quiz_ids = [q.id for q in db.query(models.Quiz.id).filter(
        models.Quiz.topic_id.in_(topic_ids)).all()] if topic_ids else []

    attempt_ids = [a.id for a in db.query(models.QuizAttempt.id).filter(
        models.QuizAttempt.quiz_id.in_(quiz_ids)).all()] if quiz_ids else []

    # ── Delete in correct order (child → parent) ───────────────────────────

    # Step 1 — quiz_attempt_answers (child of quiz_attempts)
    # No SQLAlchemy model exists so use raw SQL
    if attempt_ids:
        db.execute(
            text("DELETE FROM quiz_attempt_answers WHERE attempt_id = ANY(:ids)"),
            {"ids": attempt_ids}
        )

    # Step 2 — quiz_attempts
    if quiz_ids:
        db.query(models.QuizAttempt).filter(
            models.QuizAttempt.quiz_id.in_(quiz_ids)
        ).delete(synchronize_session=False)

    # Step 3 — quiz_questions
    if quiz_ids:
        db.query(models.QuizQuestion).filter(
            models.QuizQuestion.quiz_id.in_(quiz_ids)
        ).delete(synchronize_session=False)

    # Step 4 — quizzes
    if topic_ids:
        db.query(models.Quiz).filter(
            models.Quiz.topic_id.in_(topic_ids)
        ).delete(synchronize_session=False)

    # Step 5 — assignment_submissions
    assign_ids = [a.id for a in db.query(models.Assignment.id).filter(
        models.Assignment.topic_id.in_(topic_ids)).all()] if topic_ids else []

    if assign_ids:
        db.query(models.AssignmentSubmission).filter(
            models.AssignmentSubmission.assignment_id.in_(assign_ids)
        ).delete(synchronize_session=False)

    # Step 6 — assignments
    if topic_ids:
        db.query(models.Assignment).filter(
            models.Assignment.topic_id.in_(topic_ids)
        ).delete(synchronize_session=False)

    # Step 7 — video_progress
    video_ids = [v.id for v in db.query(models.Video.id).filter(
        models.Video.topic_id.in_(topic_ids)).all()] if topic_ids else []

    if video_ids:
        db.query(models.VideoProgress).filter(
            models.VideoProgress.video_id.in_(video_ids)
        ).delete(synchronize_session=False)

    # Step 8 — videos
    if topic_ids:
        db.query(models.Video).filter(
            models.Video.topic_id.in_(topic_ids)
        ).delete(synchronize_session=False)

    # Step 9 — materials
    if course_id:
        db.query(models.Material).filter(
            models.Material.course_id == course_id
        ).delete(synchronize_session=False)

    # Step 10 — topics
    if topic_ids:
        db.query(models.Topic).filter(
            models.Topic.id.in_(topic_ids)
        ).delete(synchronize_session=False)

    # Step 11 — enrollments
    db.query(models.Enrollment).filter(
        models.Enrollment.course_id == course_id
    ).delete(synchronize_session=False)

    # Step 12 — certificates
    db.query(models.Certificate).filter(
        models.Certificate.course_id == course_id
    ).delete(synchronize_session=False)

    # Step 13 — the course itself
    db.delete(course)
    db.commit()

    return {"message": "Course deleted successfully"}


@router.get("/courses/{course_id}/topics")
def get_topics_by_course(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    return db.query(models.Topic).filter(
        models.Topic.course_id == course_id
    ).all()


@router.get("/courses/{course_id}/stats")
def get_course_stats(
    course_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.organization_id == teacher.organization_id
    ).first()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    total_topics = db.query(models.Topic).filter(
        models.Topic.course_id == course_id
    ).count()

    # Get actual list of topic IDs to avoid Subquery boolean errors
    topic_id_list = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course_id).all()]

    total_quizzes = db.query(models.Quiz).filter(
        models.Quiz.topic_id.in_(topic_id_list)
    ).count() if topic_id_list else 0

    total_assignments = db.query(models.Assignment).filter(
        models.Assignment.topic_id.in_(topic_id_list)
    ).count() if topic_id_list else 0

    enrolled_students = db.query(models.Enrollment).filter(
        models.Enrollment.course_id == course_id
    ).count()

    certificates_issued = db.query(models.Certificate).filter(
        models.Certificate.course_id == course_id,
        models.Certificate.issued == True
    ).count()

    total_materials = db.query(models.Material).filter(
        models.Material.course_id == course_id
    ).count()

    # ── Engagement for this course ──
    total_enrolled = enrolled_students
    
    # 1. Video Rate
    video_ids = [v[0] for v in db.query(models.Video.id).filter(models.Video.topic_id.in_(topic_id_list)).all()] if topic_id_list else []
    potential_views = len(video_ids) * total_enrolled
    actual_completions = db.query(models.VideoProgress).filter(
        models.VideoProgress.video_id.in_(video_ids),
        models.VideoProgress.watch_percentage >= 80
    ).count() if video_ids else 0
    video_rate = round((actual_completions / potential_views * 100), 1) if potential_views > 0 else 0

    # 2. Quiz Rate
    quiz_ids = [q[0] for q in db.query(models.Quiz.id).filter(models.Quiz.topic_id.in_(topic_id_list)).all()] if topic_id_list else []
    potential_quizzes = len(quiz_ids) * total_enrolled
    actual_attempts = db.query(models.QuizAttempt).filter(models.QuizAttempt.quiz_id.in_(quiz_ids)).count() if quiz_ids else 0
    quiz_rate = round((actual_attempts / potential_quizzes * 100), 1) if potential_quizzes > 0 else 0

    # 3. Assignment Rate
    assign_ids = [a[0] for a in db.query(models.Assignment.id).filter(models.Assignment.topic_id.in_(topic_id_list)).all()] if topic_id_list else []
    potential_assigns = len(assign_ids) * total_enrolled
    actual_subs = db.query(models.AssignmentSubmission).filter(models.AssignmentSubmission.assignment_id.in_(assign_ids)).count() if assign_ids else 0
    assign_rate = round((actual_subs / potential_assigns * 100), 1) if potential_assigns > 0 else 0

    return {
        "enrolled_students":   enrolled_students,
        "total_topics":        total_topics,
        "total_quizzes":       total_quizzes,
        "total_assignments":   total_assignments,
        "total_materials":     total_materials,
        "certificates_issued": certificates_issued,
        "engagement": {
            "video_rate": video_rate,
            "quiz_rate": quiz_rate,
            "assign_rate": assign_rate
        }
    }

# ── TEACHER CERTIFICATES ─────────────────────────────────────────────────────
from routers.dashboard import get_student_metrics
from datetime import datetime

@router.get("/certificates/requests")
def get_teacher_pending_requests(db: Session = Depends(get_db), teacher: models.User = Depends(get_current_teacher)):
    # Get pending certificates for courses created by this teacher
    reqs = db.query(models.Certificate, models.User.name, models.User.email, models.Course.title)\
        .join(models.User, models.Certificate.student_id == models.User.id)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(models.Course.created_by == teacher.id)\
        .filter(models.Certificate.status == "pending")\
        .all()
    
    result = []
    for cert, name, email, title in reqs:
        # Get student score for this course
        m, l, r = get_student_metrics(db, cert.student_id, cert.course_id)
        result.append({
            "id": cert.id, "student_name": name, "student_email": email,
            "course_title": title, "score": round(m["overall_score"]),
            "completion": round(m["completion_rate"]),
            "request_date": cert.request_date.isoformat() if cert.request_date else None
        })
    return result

@router.post("/certificates/{cert_id}/issue")
def issue_teacher_certificate(cert_id: int, db: Session = Depends(get_db), teacher: models.User = Depends(get_current_teacher)):
    cert = db.query(models.Certificate).join(models.Course).filter(
        models.Certificate.id == cert_id,
        models.Course.created_by == teacher.id
    ).first()
    if not cert: raise HTTPException(status_code=404, detail="Request not found or access denied")
    
    cert.status = "verified"
    cert.issued = True
    cert.issued_at = datetime.utcnow()
    db.commit()

    # Notify Student
    course = db.query(models.Course).filter(models.Course.id == cert.course_id).first()
    create_notification(
        db, cert.student_id, 
        "Certificate Issued! 🎓", 
        f"Congratulations! Your teacher has issued your certificate for {course.title if course else 'your course'}.",
        "student-performnace.html"
    )

    return {"message": "Certificate issued"}

@router.post("/certificates/{cert_id}/reject")
def reject_teacher_certificate(cert_id: int, db: Session = Depends(get_db), teacher: models.User = Depends(get_current_teacher)):
    cert = db.query(models.Certificate).join(models.Course).filter(
        models.Certificate.id == cert_id,
        models.Course.created_by == teacher.id
    ).first()
    if not cert: raise HTTPException(status_code=404, detail="Request not found or access denied")
    
    cert.status = "rejected"
    db.commit()

    # Notify Student
    course = db.query(models.Course).filter(models.Course.id == cert.course_id).first()
    create_notification(
        db, cert.student_id, 
        "Certificate Request Update", 
        f"Your teacher did not approve your certificate request for {course.title if course else 'your course'} at this time.",
        "student-performnace.html"
    )

    return {"message": "Request rejected"}

@router.get("/certificates/issued")
def get_teacher_issued_certificates(db: Session = Depends(get_db), teacher: models.User = Depends(get_current_teacher)):
    issued = db.query(models.Certificate, models.User.name, models.Course.title)\
        .join(models.User, models.Certificate.student_id == models.User.id)\
        .join(models.Course, models.Certificate.course_id == models.Course.id)\
        .filter(models.Course.created_by == teacher.id)\
        .filter(models.Certificate.issued == True)\
        .all()
    
    return [{
        "id": c.id, "student_name": name, "course_title": title,
        "issued_at": c.issued_at.isoformat() if c.issued_at else None
    } for c, name, title in issued]
