"""Application settings, read from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (no extra dependency): KEY=VALUE lines; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'bookrec.db'}")
SEED_ON_STARTUP = os.getenv("SEED_ON_STARTUP", "true").lower() in {"1", "true", "yes"}

# Demo admin created by the seed script (change after first login!)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@bookrec.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@12345")
