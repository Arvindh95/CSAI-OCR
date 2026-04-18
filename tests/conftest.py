import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_KEY_PEPPER", "0" * 32)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ocr_user:test@127.0.0.1:5432/ocr_billing",
)
