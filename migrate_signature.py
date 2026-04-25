from sqlalchemy import text
from database import engine

def migrate():
    print("Connecting to database...")
    with engine.connect() as conn:
        print("Checking for signature_url column in organizations table...")
        try:
            # Check if column exists
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='organizations' AND column_name='signature_url'"))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding signature_url column to organizations table...")
                conn.execute(text("ALTER TABLE organizations ADD COLUMN signature_url VARCHAR"))
                conn.commit() 
                print("Migration successful: signature_url column added.")
            else:
                print("Column signature_url already exists. Skipping.")
        except Exception as e:
            print(f"Error during migration: {str(e)}")

if __name__ == "__main__":
    migrate()
