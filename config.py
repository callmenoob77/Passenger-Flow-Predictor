import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)

CONN = os.getenv("SUPABASE_CONN_STRING")  # None → DB features disabled (demo mode)

