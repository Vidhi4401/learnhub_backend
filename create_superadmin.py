from database import SessionLocal
import models
from auth import hash_password

def create_superadmin():
    db = SessionLocal()
    try:
        # Superadmin configuration
        data = {
            "name": "Super Admin",
            "email": "superadmin@gmail.com",
            "password": "superadmin123",
            "role": "superadmin"
        }

        # Check if email exists
        existing = db.query(models.User).filter(models.User.email == data["email"]).first()
        if existing:
            print(f"User with email {data['email']} already exists. Updating role to superadmin...")
            existing.role = "superadmin"
            db.commit()
            print("✅ Role updated to superadmin.")
        else:
            # We might need an organization even for superadmin if the DB schema requires it
            # or we can try None if it's allowed. 
            # Looking at create_admin.py, it uses org ID 1.
            
            new_user = models.User(
                name=data["name"],
                email=data["email"],
                password_hash=hash_password(data["password"]),
                role=data["role"],
                organization_id=None, # Try None first
                status=True
            )
            db.add(new_user)
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                print("Could not create without organization_id. Using default org (ID 1)...")
                # Fallback to org 1 if None is not allowed
                org = db.query(models.Organization).first()
                if not org:
                    org = models.Organization(name="System", platform_name="System", email="system@example.com")
                    db.add(org)
                    db.commit()
                    db.refresh(org)
                
                new_user.organization_id = org.id
                db.add(new_user)
                db.commit()

            print(f"✅ Superadmin created: {data['name']} ({data['email']})")
            print(f"Password: {data['password']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_superadmin()
