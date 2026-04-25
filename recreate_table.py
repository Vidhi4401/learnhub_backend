from database import engine, Base
import models
from sqlalchemy import text

def reset_database():
    print("--- 🚨 Reseting ALL Database Tables 🚨 ---")
    try:
        # This will drop all tables defined in models.py
        print("1. Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
        print("   ✅ All tables dropped.")

        print("2. Re-creating all tables from scratch...")
        # This will create everything defined in models.py including the new columns
        Base.metadata.create_all(bind=engine)
        print("   ✅ Database schema re-synced.")
        
        print("\n🎉 SUCCESS! All tables (including Certificates) are now up to date.")
        print("NOTE: You will need to create your Admin user again.")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    reset_database()
