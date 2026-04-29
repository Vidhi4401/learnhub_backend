from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from auth import hash_password, verify_password
from dependencies import get_current_user
from typing import List

router = APIRouter(prefix="/api/v1/superadmin", tags=["Super Admin"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_superadmin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return current_user

# ── ORGANIZATIONS ──
@router.get("/organizations", response_model=List[schemas.OrganizationResponse])
def get_organizations(db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    return db.query(models.Organization).all()

@router.post("/organizations", response_model=schemas.OrganizationResponse)
def create_organization(org: schemas.OrganizationCreate, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    # Check if org name exists
    existing_org = db.query(models.Organization).filter(models.Organization.name == org.name).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name already exists")

    # Check if admin email exists
    existing_user = db.query(models.User).filter(models.User.email == org.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already registered")

    # Create organization
    db_org = models.Organization(
        name=org.name,
        platform_name=org.platform_name,
        email=org.admin_email
    )
    db.add(db_org)
    db.commit()
    db.refresh(db_org)

    # Create admin user
    hashed_password = hash_password(org.admin_password)
    db_admin = models.User(
        name=org.admin_name,
        email=org.admin_email,
        password_hash=hashed_password,
        role="admin",
        organization_id=db_org.id
    )
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)

    return db_org

@router.delete("/organizations/{org_id}")
def delete_organization(org_id: int, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Delete all users in this org first (avoids FK constraint errors)
    db.query(models.User).filter(models.User.organization_id == org_id).delete()
    db.delete(org)
    db.commit()
    return {"message": "Organization deleted successfully"}

# ── ADMINS ──
@router.get("/admins")
def get_all_admins(db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    admins = db.query(models.User, models.Organization.name.label("org_name"))\
        .join(models.Organization, models.User.organization_id == models.Organization.id)\
        .filter(models.User.role == "admin").all()

    return [{
        "id": a.User.id,
        "name": a.User.name,
        "email": a.User.email,
        "org_name": a.org_name,
        "status": a.User.status
    } for a in admins]

@router.post("/admins")
def create_org_admin(admin_data: schemas.UserCreate, org_id: int, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    # Check if org exists
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check if email exists
    existing = db.query(models.User).filter(models.User.email == admin_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_admin = models.User(
        name=admin_data.name,
        email=admin_data.email,
        password_hash=hash_password(admin_data.password),
        role="admin",
        organization_id=org_id
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return {"message": "Admin created successfully", "id": new_admin.id}

@router.delete("/admins/{user_id}")
def delete_admin(user_id: int, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    admin = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.role == "admin"
    ).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    db.delete(admin)
    db.commit()
    return {"message": "Admin deleted successfully"}

# ── CONTACT REQUESTS ──
@router.get("/contact-requests", response_model=List[schemas.ContactRequestResponse])
def get_contact_requests(db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    return db.query(models.ContactRequest).filter(models.ContactRequest.status == "pending").all()

@router.post("/contact")
def contact_us(req: schemas.ContactRequestCreate, db: Session = Depends(get_db)):
    # Check if org name exists
    existing_org = db.query(models.Organization).filter(models.Organization.name == req.org_name).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name already exists")

    # Check if org name in contact requests (only if pending)
    existing_req = db.query(models.ContactRequest).filter(
        models.ContactRequest.org_name == req.org_name,
        models.ContactRequest.status == "pending"
    ).first()
    if existing_req:
        raise HTTPException(status_code=400, detail="Organization already has a pending request")

    # Check if admin email exists
    existing_user = db.query(models.User).filter(models.User.email == req.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already registered")

    # Check if email in contact requests (only if pending)
    existing_email = db.query(models.ContactRequest).filter(
        models.ContactRequest.admin_email == req.admin_email,
        models.ContactRequest.status == "pending"
    ).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already has a pending request")

    hashed_password = hash_password(req.admin_password)
    contact_request = models.ContactRequest(
        org_name=req.org_name,
        admin_name=req.admin_name,
        admin_email=req.admin_email,
        admin_password=hashed_password,
        status="pending"
    )
    db.add(contact_request)
    db.commit()
    db.refresh(contact_request)

    return {"message": "Contact request submitted successfully. Please wait for admin approval."}

@router.post("/approve-contact/{request_id}")
def approve_contact(request_id: int, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    contact_req = db.query(models.ContactRequest).filter(models.ContactRequest.id == request_id).first()
    if not contact_req:
        raise HTTPException(status_code=404, detail="Contact request not found")
    if contact_req.status != "pending":
        raise HTTPException(status_code=400, detail="Contact request is not pending")

    existing_org = db.query(models.Organization).filter(models.Organization.name == contact_req.org_name).first()
    if existing_org:
        raise HTTPException(status_code=400, detail="Organization name already exists")

    existing_user = db.query(models.User).filter(models.User.email == contact_req.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already registered")

    db_org = models.Organization(
        name=contact_req.org_name,
        platform_name=contact_req.org_name,
        email=contact_req.admin_email
    )
    db.add(db_org)
    db.commit()
    db.refresh(db_org)

    db_admin = models.User(
        name=contact_req.admin_name,
        email=contact_req.admin_email,
        password_hash=contact_req.admin_password,
        role="admin",
        organization_id=db_org.id
    )
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)

    contact_req.status = "approved"
    db.commit()

    return {"message": "Contact request approved. Organization and admin created successfully."}

@router.post("/reject-contact/{request_id}")
def reject_contact(request_id: int, db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    contact_req = db.query(models.ContactRequest).filter(models.ContactRequest.id == request_id).first()
    if not contact_req:
        raise HTTPException(status_code=404, detail="Contact request not found")
    if contact_req.status != "pending":
        raise HTTPException(status_code=400, detail="Contact request is not pending")

    contact_req.status = "rejected"
    db.commit()

    return {"message": "Contact request rejected."}

# ── MESSAGES ──
@router.get("/messages", response_model=List[schemas.MessageResponse])
def get_messages(db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    return db.query(models.Message).all()

# ── DASHBOARD ──
@router.get("/dashboard")
def get_super_dashboard(db: Session = Depends(get_db), superadmin=Depends(get_current_superadmin)):
    total_orgs     = db.query(models.Organization).count()
    total_admins   = db.query(models.User).filter(models.User.role == "admin").count()
    total_teachers = db.query(models.User).filter(models.User.role == "teacher").count()
    total_students = db.query(models.User).filter(models.User.role == "student").count()
    total_courses  = db.query(models.Course).count()
    pending_requests = db.query(models.ContactRequest).filter(models.ContactRequest.status == "pending").count()

    return {
        "total_organizations": total_orgs,
        "total_admins":        total_admins,
        "total_teachers":      total_teachers,
        "total_students":      total_students,
        "total_users":         total_admins + total_teachers + total_students,
        "total_courses":       total_courses,
        "pending_requests":    pending_requests,
    }
