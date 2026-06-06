import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
dotenv_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path)

CONN = os.getenv("SUPABASE_CONN_STRING")
if not CONN:
    raise ValueError(
        "SUPABASE_CONN_STRING environment variable is not set. "
        "Please copy .env.example to .env and configure your connection string."
    )

