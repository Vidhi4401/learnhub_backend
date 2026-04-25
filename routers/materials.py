from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from dependencies import get_current_teacher, get_current_user
from cloudinary_utils import upload_to_cloudinary

router = APIRouter(prefix="/api/v1/materials", tags=["Materials"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Upload Material (Teacher only) ────────────────────────────────────────────
@router.post("/upload")
async def upload_material(
    title: str = Form(...),
    course_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    # Verify teacher owns this course
    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.created_by == teacher.id
    ).first()
    if not course:
        raise HTTPException(status_code=403,
                            detail="You can only upload materials for your own courses")

    # Upload to Cloudinary (auto-detect type for PDFs/docs)
    secure_url = upload_to_cloudinary(file, folder="learnhub/materials", resource_type="auto")
    if not secure_url:
        raise HTTPException(status_code=500, detail="File upload to Cloudinary failed")

    new_material = models.Material(
        title=title,
        file_url=secure_url,
        course_id=course_id,
        teacher_id=teacher.id
    )
    db.add(new_material)
    db.commit()
    db.refresh(new_material)

    return {"message": "Material uploaded successfully", "id": new_material.id,
            "file_url": secure_url}


# ── Get Materials for a Course (Student/Teacher) ──────────────────────────────
@router.get("/course/{course_id}")
def get_course_materials(
    course_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    # Students must be enrolled
    if user.role == "student":
        enrolled = db.query(models.Enrollment).filter(
            models.Enrollment.course_id  == course_id,
            models.Enrollment.student_id == user.id
        ).first()
        if not enrolled:
            raise HTTPException(status_code=403,
                                detail="You must be enrolled to view materials")

    materials = db.query(models.Material).filter(
        models.Material.course_id == course_id
    ).order_by(models.Material.created_at.desc()).all()

    return [
        {
            "id":        m.id,
            "title":     m.title,
            "file_url":  m.file_url,
            "course_id": m.course_id,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in materials
    ]


# ── Delete Material (Teacher only, own materials) ─────────────────────────────
@router.delete("/{material_id}")
def delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    material = db.query(models.Material).filter(
        models.Material.id         == material_id,
        models.Material.teacher_id == teacher.id
    ).first()
    if not material:
        raise HTTPException(status_code=404,
                            detail="Material not found or unauthorized")

    # File is on Cloudinary — no local deletion needed
    db.delete(material)
    db.commit()
    return {"message": "Material deleted"}