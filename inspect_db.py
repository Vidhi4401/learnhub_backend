from database import engine
from sqlalchemy import text

def inspect_constraint():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT conname, pg_get_constraintdef(c.oid) 
            FROM pg_constraint c 
            JOIN pg_namespace n ON n.oid = c.connamespace 
            WHERE conname = 'users_role_check';
        """))
        for row in result:
            print(f"Constraint: {row[0]}")
            print(f"Definition: {row[1]}")

if __name__ == "__main__":
    inspect_constraint()
