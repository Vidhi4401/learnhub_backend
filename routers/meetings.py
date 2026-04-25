from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from datetime import datetime
from dependencies import get_current_teacher, get_current_user
from typing import List

router = APIRouter(prefix="/api/v1/meetings", tags=["Meetings"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from routers.notifications import create_notification

@router.post("/", response_model=schemas.MeetingResponse)
def create_meeting(
    meeting: schemas.MeetingCreate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    print(f"[Meeting] Creating: {meeting.title} for course {meeting.course_id} by teacher {teacher.id}")
    # Verify course belongs to teacher's organization
    course = db.query(models.Course).filter(
        models.Course.id == meeting.course_id,
        models.Course.organization_id == teacher.organization_id
    ).first()

    if not course:
        print(f"[Meeting Error] Course {meeting.course_id} not found or access denied")
        raise HTTPException(status_code=404, detail="Course not found or access denied")

    try:
        db_meeting = models.Meeting(
            title=meeting.title,
            description=meeting.description,
            meeting_link=meeting.meeting_link,
            meeting_date=meeting.meeting_date,
            course_id=meeting.course_id,
            teacher_id=teacher.id
        )
        db.add(db_meeting)
        db.commit()
        db.refresh(db_meeting)
        
        # Notify all enrolled students
        enrolled_students = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == meeting.course_id
        ).all()
        
        for (sid,) in enrolled_students:
            create_notification(
                db, sid,
                "New Meeting Scheduled",
                f"A new live session '{meeting.title}' has been scheduled for {course.title}.",
                "student-meetings.html"
            )

        print(f"[Meeting Success] Created meeting ID: {db_meeting.id}")
        return db_meeting
    except Exception as e:
        db.rollback()
        print(f"[Meeting DB Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

from datetime import datetime

@router.get("/teacher", response_model=List[schemas.MeetingResponse])
def get_teacher_meetings(
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    now = datetime.utcnow()
    # 1. Automatically delete past meetings
    db.query(models.Meeting).filter(
        models.Meeting.teacher_id == teacher.id,
        models.Meeting.meeting_date < now
    ).delete()
    db.commit()

    # 2. Return current/future meetings
    return db.query(models.Meeting).filter(
        models.Meeting.teacher_id == teacher.id,
        models.Meeting.meeting_date >= now
    ).all()

@router.get("/course/{course_id}", response_model=List[schemas.MeetingResponse])
def get_course_meetings(
    course_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    now = datetime.utcnow()
    # Check if user is enrolled or is the teacher
    if user.role == "student":
        enrollment = db.query(models.Enrollment).filter(
            models.Enrollment.course_id == course_id,
            models.Enrollment.student_id == user.id
        ).first()
        if not enrollment:
            raise HTTPException(status_code=403, detail="Not enrolled in this course")
    
    # Return current/future meetings
    return db.query(models.Meeting).filter(
        models.Meeting.course_id == course_id,
        models.Meeting.meeting_date >= now
    ).all()

@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    meeting = db.query(models.Meeting).filter(
        models.Meeting.id == meeting_id,
        models.Meeting.teacher_id == teacher.id
    ).first()
    
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted"}
