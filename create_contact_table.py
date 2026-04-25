from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS contact_requests (
            id SERIAL PRIMARY KEY,
            org_name VARCHAR UNIQUE,
            admin_name VARCHAR,
            admin_email VARCHAR UNIQUE,
            admin_password VARCHAR,
            status VARCHAR DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.commit()
    print("contact_requests table created successfully")
