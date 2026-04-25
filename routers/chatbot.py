from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from typing import List
from groq import Groq
import os
from config import GROQ_API_KEY
from dependencies import get_current_user, get_db
from routers.notifications import create_notification

router = APIRouter(prefix="/api/v1/chat", tags=["Chatbot"])

# Ensure the key is stripped of any surrounding whitespace
STRIPPED_KEY = GROQ_API_KEY.strip() if GROQ_API_KEY else ""
client = Groq(api_key=STRIPPED_KEY)

@router.post("/ai-ask")
def ai_ask_only(data: schemas.ChatDoubtCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """AI response with database storage for persistent history."""
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful and concise AI Tutor for LearnHub. Answer the student's doubt clearly."},
                {"role": "user", "content": data.query}
            ],
        )
        ai_response = completion.choices[0].message.content

        # Save to DB for history persistence
        new_doubt = models.ChatDoubt(
            student_id=current_user.id,
            query=data.query,
            response=ai_response,
            mode="AI",
            is_read_by_student=True,
            is_read_by_faculty=False,
            course_id=data.course_id,
            topic_id=data.topic_id
        )
        db.add(new_doubt)
        db.commit()

        return {"response": ai_response, "mode": "AI"}
    except Exception as e:
        print(f"[Chatbot] AI-Only Error: {str(e)}")
        return {"response": "I'm having trouble connecting to my AI brain right now.", "mode": "AI"}

@router.post("/ask", response_model=schemas.ChatDoubtResponse)
def ask_question(data: schemas.ChatDoubtCreate, student_id: int, db: Session = Depends(get_db)):
    try:
        # 1. Determine Faculty ID
        # Priority 1: Manually selected teacher from the dropdown
        faculty_id = data.faculty_id
        target_course_id = data.course_id

        # Priority 2: If no manual selection, try to find course creator
        if not faculty_id:
            if data.topic_id:
                topic = db.query(models.Topic).filter(models.Topic.id == data.topic_id).first()
                if topic:
                    target_course_id = topic.course_id

            if target_course_id:
                course = db.query(models.Course).filter(models.Course.id == target_course_id).first()
                if course:
                    faculty_id = course.created_by
        
        print(f"[Chatbot] New doubt from Student {student_id}. Target Faculty: {faculty_id}")

        # 2. Create the doubt record
        new_doubt = models.ChatDoubt(
            student_id=student_id,
            query=data.query,
            topic_id=data.topic_id,
            course_id=target_course_id,
            faculty_id=faculty_id,      # Now strictly targeted
            mode=data.mode,
            is_read_by_faculty=(data.mode == "FACULTY"), 
            is_read_by_student=True 
        )
        
        # 3. If AI mode, generate real response from GROQ
        if data.mode == "AI":
            try:
                print(f"[Chatbot] Attempting AI completion with key starting with: {STRIPPED_KEY[:8]}...")
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are a helpful and concise AI Tutor for LearnHub. Answer the student's doubt about their studies clearly and encouragingly."},
                        {"role": "user", "content": data.query}
                    ],
                )
                new_doubt.response = completion.choices[0].message.content
                print("[Chatbot] AI response received successfully.")
            except Exception as e:
                print(f"[Chatbot] AI Error: {str(e)}")
                # Fallback if AI fails (e.g., rate limit)
                new_doubt.mode = "FACULTY"
                new_doubt.is_read_by_faculty = True
                new_doubt.response = "I'm having a little trouble connecting to my AI brain. I've sent your query to the faculty instead! They'll get back to you soon."
        
        db.add(new_doubt)
        db.commit()
        db.refresh(new_doubt)

        # Notify Faculty if mode is FACULTY
        if data.mode == "FACULTY" and faculty_id:
            student = db.query(models.User).filter(models.User.id == student_id).first()
            course = db.query(models.Course).filter(models.Course.id == target_course_id).first()
            create_notification(
                db, faculty_id,
                "New Student Doubt",
                f"Student {student.name if student else 'A student'} has a question about {course.title if course else 'your course'}: '{data.query[:50]}...'",
                "doubts.html"
            )

        return new_doubt
    except Exception as e:
        print(f"[Chatbot] ERROR in ask_question: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.get("/history", response_model=List[schemas.ChatDoubtResponse])
def get_chat_history(student_id: int, db: Session = Depends(get_db)):
    return db.query(models.ChatDoubt).filter(
        models.ChatDoubt.student_id == student_id
    ).order_by(models.ChatDoubt.created_at.asc()).all()

@router.get("/unread-count", response_model=schemas.UnreadCountResponse)
def get_unread_count(user_id: int, role: str, db: Session = Depends(get_db)):
    if role == "student":
        count = db.query(models.ChatDoubt).filter(
            models.ChatDoubt.student_id == user_id,
            models.ChatDoubt.is_read_by_student == False,
            models.ChatDoubt.response != None
        ).count()
    else:
        # Teachers ONLY see doubts specifically assigned to them
        count = db.query(models.ChatDoubt).filter(
            models.ChatDoubt.mode == "FACULTY",
            models.ChatDoubt.faculty_id == user_id,
            models.ChatDoubt.response == None
        ).count()
    return {"count": count}

@router.post("/mark-read")
def mark_as_read(user_id: int, role: str, db: Session = Depends(get_db)):
    if role == "student":
        db.query(models.ChatDoubt).filter(
            models.ChatDoubt.student_id == user_id,
            models.ChatDoubt.is_read_by_student == False
        ).update({"is_read_by_student": True})
    else:
        db.query(models.ChatDoubt).filter(
            models.ChatDoubt.faculty_id == user_id,
            models.ChatDoubt.is_read_by_faculty == False
        ).update({"is_read_by_faculty": True})
    db.commit()
    return {"message": "Success"}

@router.get("/teachers", response_model=List[schemas.UserResponse])
def get_available_teachers(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Returns all active teachers in the organization."""
    return db.query(models.User).filter(
        models.User.organization_id == current_user.organization_id,
        models.User.role == "teacher",
        models.User.status == True
    ).all()

# ── Faculty Portal Endpoints ──

@router.get("/faculty/doubts", response_model=List[schemas.ChatDoubtResponse])
def get_faculty_doubts(faculty_id: int, filter: str = "pending", db: Session = Depends(get_db)):
    """Teachers ONLY see doubts directed to them."""
    base_query = db.query(models.ChatDoubt, models.User.name.label("student_name")).join(
        models.User, models.ChatDoubt.student_id == models.User.id
    ).filter(models.ChatDoubt.faculty_id == faculty_id)

    if filter == "pending":
        results = base_query.filter(
            models.ChatDoubt.mode == "FACULTY",
            models.ChatDoubt.response == None
        ).order_by(models.ChatDoubt.created_at.desc()).all()
    else:
        results = base_query.order_by(models.ChatDoubt.created_at.desc()).all()
    
    doubts = []
    for doubt, student_name in results:
        doubt_dict = {c.name: getattr(doubt, c.name) for c in doubt.__table__.columns}
        doubt_dict["student_name"] = student_name
        doubts.append(doubt_dict)
        
    return doubts

    # if filter == "pending":
    #     # Only show Faculty doubts for this specific teacher that haven't been answered yet
    #     results = base_query.filter(
    #         models.ChatDoubt.mode == "FACULTY",
    #         models.ChatDoubt.response == None
    #     ).order_by(models.ChatDoubt.created_at.desc()).all()
    # else:
    #     # Show all history for this teacher
    #     results = base_query.order_by(models.ChatDoubt.created_at.desc()).all()
    
    # doubts = []
    # for doubt, student_name in results:
    #     doubt_dict = {c.name: getattr(doubt, c.name) for c in doubt.__table__.columns}
    #     doubt_dict["student_name"] = student_name
    #     doubts.append(doubt_dict)
        
    # return doubts

@router.post("/faculty/reply")
def reply_to_doubt(data: schemas.FacultyReplySchema, db: Session = Depends(get_db)):
    doubt = db.query(models.ChatDoubt).filter(models.ChatDoubt.id == data.doubt_id).first()
    if not doubt:
        raise HTTPException(status_code=404, detail="Doubt not found")
    
    doubt.response = data.response
    doubt.faculty_id = data.faculty_id
    doubt.is_read_by_student = False 
    doubt.is_read_by_faculty = True 
    
    db.commit()

    # Notify Student
    create_notification(
        db, doubt.student_id, 
        "Doubt Answered", 
        f"A teacher has replied to your doubt: {data.response[:50]}...",
        "student-courses.html"
    )

    return {"message": "Reply sent successfully"}
