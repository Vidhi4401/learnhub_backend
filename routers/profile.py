from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from auth import hash_password
from dependencies import get_current_user

router = APIRouter(prefix="/api/v1/teacher", tags=["Profile"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/profile")
def get_teacher_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "name": user.name, "email": user.email}


@router.put("/profile")
def update_teacher_profile(
    name:     str = Form(None),
    email:    str = Form(None),
    password: str = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if name:  user.name  = name
    if email: user.email = email

    if password:
        user.password_hash = hash_password(password)

    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email}
