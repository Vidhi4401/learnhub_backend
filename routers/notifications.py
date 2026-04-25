from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from dependencies import get_current_user
from typing import List

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
def get_my_notifications(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch recent notifications for the logged-in user."""
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).order_by(models.Notification.created_at.desc()).limit(20).all()
    
    return notifications

@router.get("/unread-count")
def get_unread_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the count of unread notifications."""
    count = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False
    ).count()
    return {"count": count}

@router.post("/{notif_id}/read")
def mark_as_read(
    notif_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a specific notification as read."""
    notif = db.query(models.Notification).filter(
        models.Notification.id == notif_id,
        models.Notification.user_id == current_user.id
    ).first()
    
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notif.is_read = True
    db.commit()
    return {"message": "Marked as read"}

@router.post("/read-all")
def mark_all_read(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications for the user as read."""
    db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}

# Utility function to create notifications from other routers
def create_notification(db: Session, user_id: int, title: str, message: str, link: str = None):
    new_notif = models.Notification(
        user_id=user_id,
        title=title,
        message=message,
        link=link
    )
    db.add(new_notif)
    db.commit()
