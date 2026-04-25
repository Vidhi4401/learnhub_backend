from database import engine
from sqlalchemy import text, inspect

def migrate():
    print("--- 🛠 Running Database Migration (Adding Missing Columns) 🛠 ---")
    inspector = inspect(engine)
    
    with engine.connect() as conn:
        # 1. Check Certificates table
        columns = [c['name'] for c in inspector.get_columns('certificates')]
        
        if 'status' not in columns:
            print("Adding 'status' to certificates...")
            conn.execute(text("ALTER TABLE certificates ADD COLUMN status VARCHAR(20) DEFAULT 'pending';"))
        
        if 'request_date' not in columns:
            print("Adding 'request_date' to certificates...")
            conn.execute(text("ALTER TABLE certificates ADD COLUMN request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))

        if 'issued_at' not in columns:
            print("Adding 'issued_at' to certificates...")
            conn.execute(text("ALTER TABLE certificates ADD COLUMN issued_at TIMESTAMP;"))

        # 2. Check Student Performance table
        columns_perf = [c['name'] for c in inspector.get_columns('student_performance_summary')]
        
        if 'dropout_risk' not in columns_perf:
            print("Adding 'dropout_risk' to performance table...")
            conn.execute(text("ALTER TABLE student_performance_summary ADD COLUMN dropout_risk VARCHAR(20) DEFAULT 'Low';"))

        if 'global_learner_level' not in columns_perf:
            print("Adding 'global_learner_level' to performance table...")
            conn.execute(text("ALTER TABLE student_performance_summary ADD COLUMN global_learner_level VARCHAR(20);"))

        # 3. Check Assignments table
        columns_assign = [c['name'] for c in inspector.get_columns('assignments')]
        if 'file_url' not in columns_assign:
            print("Adding 'file_url' to assignments table...")
            conn.execute(text("ALTER TABLE assignments ADD COLUMN file_url VARCHAR;"))

        # 4. Check Quizzes table
        columns_quiz = [c['name'] for c in inspector.get_columns('quizzes')]
        if 'num_questions' not in columns_quiz:
            print("Adding 'num_questions' to quizzes table...")
            conn.execute(text("ALTER TABLE quizzes ADD COLUMN num_questions INTEGER;"))

        # 5. Check and Create Meetings Table if missing
        print("Checking for meetings table...")
        if not inspector.has_table('meetings'):
            print("Creating 'meetings' table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    description TEXT,
                    meeting_link VARCHAR NOT NULL,
                    meeting_date TIMESTAMP NOT NULL,
                    course_id INTEGER REFERENCES courses(id),
                    teacher_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
            print("✅ Meetings table created.")
        else:
            print("✅ Meetings table already exists.")

        conn.commit()
        print("✅ Migration completed successfully!")

if __name__ == "__main__":
    migrate()
