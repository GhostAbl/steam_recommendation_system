import os
from dotenv import load_dotenv

load_dotenv()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL")
SESSION_SECRET = os.getenv("SESSION_SECRET")