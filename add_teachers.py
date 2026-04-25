from database import SessionLocal
import models
from auth import hash_password

def add_new_teachers():
    db = SessionLocal()
    try:
        # Configuration for new teachers
        new_teachers_data = [
            {"name": "Teacher Two", "email": "teacher2@gmail.com", "password": "teacher123", "org_id": 1},
            {"name": "Teacher Three", "email": "teacher3@gmail.com", "password": "teacher123", "org_id": 1}
        ]

        for data in new_teachers_data:
            # Check if email exists
            existing = db.query(models.User).filter(models.User.email == data["email"]).first()
            if existing:
                print(f"User with email {data['email']} already exists.")
                continue

            new_user = models.User(
                name=data["name"],
                email=data["email"],
                password_hash=hash_password(data["password"]),
                role="teacher",
                organization_id=data["org_id"],
                status=True
            )
            db.add(new_user)
            print(f"Added teacher: {data['name']} ({data['email']})")
        
        db.commit()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    add_new_teachers()
