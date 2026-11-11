import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    timeout: float = 30.0
    database: str = str(ROOT / "backend" / "data" / "sessions.sqlite3")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        if not 0 < timeout <= 120:
            raise ValueError("LLM_TIMEOUT_SECONDS must be in (0, 120]")
        return cls(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", ""),
            model=os.getenv("LLM_MODEL", ""), timeout=timeout,
            database=os.getenv("SESSION_DB_PATH", cls.database),
        )
