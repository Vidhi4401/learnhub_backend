from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from auth import hash_password, verify_password, create_access_token
from dependencies import get_current_admin

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Login (public) ────────────────────────────────────────────────────────────
@router.post("/login")
def login(data: schemas.LoginSchema, db: Session = Depends(get_db)):
    print(f"[Login Debug] Attempting login for email: {data.email}")
    user = db.query(models.User).filter(models.User.email == data.email).first()

    if not user:
        print(f"[Login Debug] User not found for email: {data.email}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    password_verified = verify_password(data.password, user.password_hash)
    print(f"[Login Debug] User found: {user.email}, role: {user.role}, password verified: {password_verified}")

    if not password_verified:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.status:
        raise HTTPException(status_code=403,
                            detail="Your account has been deactivated. Contact your administrator.")

    # ── Super Admin Check ──
    if user.role == "superadmin":
        token = create_access_token({
            "user_id":         user.id,
            "role":            user.role,
            "organization_id": None
        })
        return {
            "success":       True,
            "id":            user.id,
            "name":          user.name,
            "email":         user.email,
            "role":          user.role,
            "access_token":  token,
            "platform_name": "LearnHub Global",
            "org_name":      "LearnHub Global",
            "org_logo":      None
        }

    org = db.query(models.Organization).filter(
        models.Organization.id == user.organization_id
    ).first()

    token = create_access_token({
        "user_id":         user.id,
        "role":            user.role,
        "organization_id": user.organization_id
    })

    return {
        "success":       True,
        "id":            user.id,
        "name":          user.name,
        "email":         user.email,
        "role":          user.role,
        "access_token":  token,
        "platform_name": org.platform_name or org.name if org else "LearnHub",
        "org_name":      org.name if org else "LearnHub",
        "org_logo":      org.logo if org else None
    }


# ── Admin: Add Student ────────────────────────────────────────────────────────
@router.post("/admin/add-student")
def admin_add_student(
    data: schemas.AdminAddUserSchema,
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role="student",
        organization_id=admin.organization_id,
        status=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Student account created", "id": new_user.id}


# ── Admin: Add Teacher ────────────────────────────────────────────────────────
@router.post("/admin/add-teacher")
def admin_add_teacher(
    data: schemas.AdminAddUserSchema,
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role="teacher",
        organization_id=admin.organization_id,
        status=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Teacher account created", "id": new_user.id}


# ── Admin: Reset Any User's Password ─────────────────────────────────────────
@router.post("/admin/reset-user-password/{user_id}")
def admin_reset_user_password(
    user_id: int,
    data: schemas.AdminPasswordReset,
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.organization_id == admin.organization_id
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot reset another admin's password")

    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": f"Password reset for {user.name}"}