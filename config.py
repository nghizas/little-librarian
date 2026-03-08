import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "data", "little-librarian.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
MAX_IMAGE_DIMENSION = 1568  # Claude's max for vision

