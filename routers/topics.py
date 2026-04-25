from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from dependencies import get_current_teacher

router = APIRouter(prefix="/api/v1/teacher", tags=["Topics"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/courses/{course_id}/topics")
def create_topic(
    course_id: int,
    data: schemas.TopicCreate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    # Calculate the next order number
    current_topics = db.query(models.Topic).filter(models.Topic.course_id == course_id).count()
    order_number = current_topics + 1
    
    topic = models.Topic(title=data.title, course_id=course_id, order_number=order_number)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return {"topic_id": topic.id}


@router.get("/topics/{topic_id}")
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    return db.query(models.Topic).filter(models.Topic.id == topic_id).first()


@router.put("/topics/{topic_id}")
def update_topic(
    topic_id: int,
    data: schemas.TopicUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    topic.title = data.title
    db.commit()
    return {"message": "Topic updated"}


@router.delete("/topics/{topic_id}")
def delete_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    db.delete(topic)
    db.commit()
    return {"message": "Topic deleted"}
