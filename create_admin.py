from database import SessionLocal
import models
from auth import hash_password

def setup_initial_data():
    db = SessionLocal()
    try:
        # 1. Ensure at least one Organization exists
        org = db.query(models.Organization).filter(models.Organization.id == 1).first()
        if not org:
            print("Creating default organization...")
            org = models.Organization(
                name="Default Org",
                platform_name="LearnHub",
                email="admin@gmail.com"
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"✅ Organization created with ID: {org.id}")

        # 2. Admin configuration
        admin_data = {
            "name": "Admin",
            "email": "admin@gmail.com",
            "password": "admin1234",
            "org_id": org.id
        }

        # Check if email exists
        existing = db.query(models.User).filter(models.User.email == admin_data["email"]).first()
        if existing:
            print(f"Admin with email {admin_data['email']} already exists.")
        else:
            new_admin = models.User(
                name=admin_data["name"],
                email=admin_data["email"],
                password_hash=hash_password(admin_data["password"]),
                role="admin",
                organization_id=admin_data["org_id"],
                status=True
            )
            db.add(new_admin)
            db.commit()
            print(f"✅ Admin created: {admin_data['name']} ({admin_data['email']})")
            print(f"Password: {admin_data['password']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_initial_data()
