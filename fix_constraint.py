from database import engine
from sqlalchemy import text

def update_role_constraint():
    print("Updating users_role_check constraint...")
    with engine.connect() as conn:
        # Drop existing constraint
        try:
            conn.execute(text("ALTER TABLE users DROP CONSTRAINT users_role_check;"))
            print("Old constraint dropped.")
        except Exception as e:
            print(f"Could not drop constraint: {e}")
        
        # Add new constraint
        try:
            conn.execute(text("""
                ALTER TABLE users ADD CONSTRAINT users_role_check 
                CHECK (role IN ('teacher', 'student', 'admin', 'superadmin'));
            """))
            conn.commit()
            print("New constraint with 'superadmin' added.")
        except Exception as e:
            print(f"Error adding new constraint: {e}")

if __name__ == "__main__":
    update_role_constraint()
