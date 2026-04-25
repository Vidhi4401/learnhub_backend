from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import SessionLocal
import models, shutil, os
from dependencies import get_current_teacher, get_current_user

router = APIRouter(prefix="/api/v1", tags=["Organization"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/organization/branding")
def get_branding(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accessible by any logged-in user (Student/Teacher/Admin) for layout branding."""
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    logo_url = org.logo
    if logo_url and not logo_url.startswith("http"):
        logo_url = f"http://127.0.0.1:8000/{logo_url}"

    return {
        "platform_name": org.platform_name or org.name,
        "logo":          logo_url
    }


from cloudinary_utils import upload_to_cloudinary

@router.get("/teacher/organization")
def get_organization(
    current_user: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Intelligent logo URL
    logo_url = org.logo
    if logo_url and not logo_url.startswith("http"):
        logo_url = f"http://127.0.0.1:8000/{logo_url}"

    return {
        "id":            org.id,
        "org_name":      org.name,
        "platform_name": org.platform_name or org.name,
        "logo":          logo_url,
        "email":         org.email,
        "status":        org.status
    }


@router.put("/teacher/organization")
def update_organization(
    platform_name: str = Form(None),
    logo: UploadFile = File(None),
    current_user: models.User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.organization_id
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if platform_name:
        org.platform_name = platform_name

    if logo and logo.filename:
        # Use Cloudinary
        cloud_url = upload_to_cloudinary(logo, folder="learnhub/logos")
        if cloud_url:
            org.logo = cloud_url

    db.commit()
    db.refresh(org)

    # Intelligent logo URL
    logo_url = org.logo
    if logo_url and not logo_url.startswith("http"):
        logo_url = f"http://127.0.0.1:8000/{logo_url}"

    return {
        "id":            org.id,
        "org_name":      org.name,
        "platform_name": org.platform_name,
        "logo":          logo_url
    }