import os
from dotenv import load_dotenv

# Use absolute path for .env file to ensure it's loaded correctly
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path, override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
CLOUDINARY_URL=os.getenv("CLOUDINARY_URL")

print(f"[Config] GROQ_API_KEY loaded, starts with: {GROQ_API_KEY[:8]}...")
print(f"[Config] GOOGLE_API_KEY loaded, starts with: {GOOGLE_API_KEY[:8]}...")
