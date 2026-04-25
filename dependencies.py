from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from auth import decode_access_token
from typing import Optional

security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    token = None
    
    # 1. Try to get token from Bearer Header
    if credentials:
        token = credentials.credentials
    
    # 2. Try to get token from Query Parameter (for browser downloads)
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(models.User).filter(
        models.User.id == payload.get("user_id")
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_current_teacher(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return current_user


def get_current_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
