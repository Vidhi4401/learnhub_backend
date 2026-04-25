from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas, json, io
from dependencies import get_current_teacher
from groq import Groq
from config import GROQ_API_KEY
from typing import Optional
from cloudinary_utils import upload_to_cloudinary, upload_buffer_to_cloudinary

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

router = APIRouter(tags=["Assignments"])

client = Groq(api_key=GROQ_API_KEY)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_assignment_pdf(title: str, description: str, total_marks: int) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    content = []
    content.append(Paragraph(f"Assignment: {title}", styles['Title']))
    content.append(Spacer(1, 12))
    content.append(Paragraph(f"Total Marks: {total_marks}", styles['Heading2']))
    content.append(Spacer(1, 12))
    
    # Split description by newlines to handle paragraphs
    for line in description.split('\n'):
        if line.strip():
            content.append(Paragraph(line, styles['Normal']))
            content.append(Spacer(1, 6))
            
    doc.build(content)
    buffer.seek(0)
    return buffer

from routers.notifications import create_notification

@router.post("/api/v1/teacher/assignments/manual")
def create_manual_assignment(
    topic_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    total_marks: int = Form(...),
    model_answer: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    file_url = None
    if file and file.filename:
        file_url = upload_to_cloudinary(file, folder="learnhub/assignments")
    else:
        # Generate PDF from description if no file provided
        pdf_buffer = generate_assignment_pdf(title, description, total_marks)
        file_url = upload_buffer_to_cloudinary(pdf_buffer, f"assignment_{title.replace(' ', '_')}.pdf", folder="learnhub/assignments")

    assignment = models.Assignment(
        topic_id=topic_id,
        title=title,
        description=description,
        total_marks=total_marks,
        model_answer=model_answer,
        file_url=file_url
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    # Notify students
    topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    if topic:
        course = db.query(models.Course).filter(models.Course.id == topic.course_id).first()
        enrolled = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == topic.course_id
        ).all()
        for (sid,) in enrolled:
            create_notification(
                db, sid,
                "New Assignment",
                f"A new assignment '{title}' has been added to {course.title if course else 'your course'}.",
                "student-assignments.html"
            )

    return {"assignment_id": assignment.id}


@router.post("/api/v1/teacher/assignments/generate-ai")
def generate_ai_assignment(
    data: schemas.AssignmentAIRequest,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    try:
        # Validate Topic
        topic = db.query(models.Topic).filter(models.Topic.id == data.topic_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        prompt = f"""
        Generate an assignment with {data.num_questions} questions for the topic "{topic.title}".
        Assignment Title: {data.title}
        Goal/Context: {data.description}
        Difficulty: {data.difficulty}
        
        Respond ONLY with a JSON object containing:
        - "description": a detailed instruction for the student (at least 3-4 sentences), including the list of questions.
        - "total_marks": int (usually between 10 and 50)
        - "model_answer": a short guide or key points for the teacher (at least 2 sentences)
        
        Example:
        {{
            "description": "...",
            "total_marks": 20,
            "model_answer": "..."
        }}
        """
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert educator. Generate assignments in JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        res_data = json.loads(completion.choices[0].message.content)
        
        description = res_data.get("description", "")
        total_marks = res_data.get("total_marks", 10)
        
        # Generate PDF for AI assignment
        pdf_buffer = generate_assignment_pdf(data.title, description, total_marks)
        file_url = upload_buffer_to_cloudinary(pdf_buffer, f"ai_assignment_{data.title.replace(' ', '_')}.pdf", folder="learnhub/assignments")

        # Create the Assignment
        assignment = models.Assignment(
            topic_id=data.topic_id,
            title=data.title,
            description=description,
            total_marks=total_marks,
            model_answer=res_data.get("model_answer", ""),
            file_url=file_url
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        
        return {"assignment_id": assignment.id, "message": "Assignment generated successfully"}
    except Exception as e:
        print(f"Error generating AI assignment: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate assignment: {str(e)}")


@router.post("/api/v1/teacher/topics/{topic_id}/assignments")
def create_assignment(
    topic_id: int,
    data: schemas.AssignmentCreate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    assignment = models.Assignment(
        topic_id=topic_id,
        title=data.title,
        description=data.description,
        total_marks=data.total_marks,
        model_answer=data.model_answer
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    # Notify students
    topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    if topic:
        course = db.query(models.Course).filter(models.Course.id == topic.course_id).first()
        enrolled = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == topic.course_id
        ).all()
        for (sid,) in enrolled:
            create_notification(
                db, sid,
                "New Assignment",
                f"A new assignment '{data.title}' has been added to {course.title if course else 'your course'}.",
                "student-assignments.html"
            )

    return {"assignment_id": assignment.id}


@router.get("/api/v1/teacher/topics/{topic_id}/assignments")
def teacher_get_assignments(
    topic_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    return db.query(models.Assignment).filter(
        models.Assignment.topic_id == topic_id
    ).all()


@router.put("/api/v1/teacher/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    data: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id
    ).first()
    assignment.title       = data.title
    assignment.description = data.description
    assignment.total_marks = data.total_marks
    assignment.model_answer= data.model_answer
    db.commit()
    return {"message": "Assignment updated"}


@router.delete("/api/v1/teacher/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    assignment = db.query(models.Assignment).filter(
        models.Assignment.id == assignment_id
    ).first()
    db.delete(assignment)
    db.commit()
    return {"message": "Assignment deleted"}

class ManualGradeIn(schemas.BaseModel):
    submission_id: int
    obtained_marks: int
    feedback: Optional[str] = None

@router.post("/api/v1/teacher/grade-submission")
def grade_submission_manually(
    data: ManualGradeIn,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    submission = db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.id == data.submission_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
        
    # Verify teacher owns the course
    assignment = db.query(models.Assignment).filter(models.Assignment.id == submission.assignment_id).first()
    topic = db.query(models.Topic).filter(models.Topic.id == assignment.topic_id).first()
    course = db.query(models.Course).filter(models.Course.id == topic.course_id).first()
    
    if course.created_by != teacher.id and teacher.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to grade this assignment")

    submission.obtained_marks = data.obtained_marks
    submission.feedback = data.feedback
    submission.is_manual_review = False
    
    db.commit()
    
    # Re-trigger certificate check
    from routers.student import check_and_auto_request_certificate
    check_and_auto_request_certificate(db, submission.student_id, course.id)
    
    return {"message": "Graded successfully"}