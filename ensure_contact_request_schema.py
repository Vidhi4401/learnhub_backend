from database import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE contact_requests ADD COLUMN IF NOT EXISTS admin_password VARCHAR"
    ))
    conn.execute(text(
        "ALTER TABLE contact_requests ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending'"
    ))
print('contact_requests schema ensured')
