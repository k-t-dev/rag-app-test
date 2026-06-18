import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    database_path: str = os.getenv("DATABASE_PATH", str(ROOT / "data" / "app.db"))
    web_origin: str = os.getenv("WEB_ORIGIN", "http://localhost:3000")


settings = Settings()

