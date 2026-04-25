from sqlalchemy import create_engine, text
from config import DATABASE_URL

# Create database engine
engine = create_engine(DATABASE_URL)

def run_migration():
    print("🚀 Starting migration for assignment_submissions table...")
    
    with engine.connect() as conn:
        # Check if columns already exist to prevent errors
        # Note: We use try/except for broader DB compatibility (SQLite/Postgres)
        
        # 1. Add student_answer column
        try:
            conn.execute(text("ALTER TABLE assignment_submissions ADD COLUMN student_answer TEXT"))
            conn.commit()
            print("✅ Added column: student_answer")
        except Exception as e:
            print(f"⚠️  Skipping student_answer: {str(e)}")

        # 2. Add feedback column
        try:
            conn.execute(text("ALTER TABLE assignment_submissions ADD COLUMN feedback TEXT"))
            conn.commit()
            print("✅ Added column: feedback")
        except Exception as e:
            print(f"⚠️  Skipping feedback: {str(e)}")

        # 3. Add is_manual_review column
        try:
            conn.execute(text("ALTER TABLE assignment_submissions ADD COLUMN is_manual_review BOOLEAN DEFAULT FALSE"))
            conn.commit()
            print("✅ Added column: is_manual_review")
        except Exception as e:
            print(f"⚠️  Skipping is_manual_review: {str(e)}")

        # 4. Ensure obtained_marks is nullable (if it wasn't)
        try:
            # PostgreSQL syntax, SQLite doesn't strictly enforce NOT NULL unless specified
            conn.execute(text("ALTER TABLE assignment_submissions ALTER COLUMN obtained_marks DROP NOT NULL"))
            conn.commit()
            print("✅ Updated: obtained_marks is now nullable")
        except Exception as e:
            print(f"ℹ️  Info (obtained_marks update): {str(e)}")

    print("\n🎉 Migration complete. No data was deleted.")

if __name__ == "__main__":
    run_migration()
