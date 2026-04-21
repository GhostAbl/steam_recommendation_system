from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:8501")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
SQL_CONNECTION_STRING = os.getenv("SQL_CONNECTION_STRING", "")

STEAM_OPENID_URL = "https://steamcommunity.com/openid"
STEAM_API_BASE = "https://api.steampowered.com"

MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"

MODELS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)