"""Runtime configuration, read from environment (.env supported)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # SQLite by default so a fresh clone runs with zero setup.
    # Production: postgresql+psycopg://user:pass@host/db (Neon, Railway, ...)
    database_url: str = Field(default=f"sqlite:///{(BACKEND_DIR / 'data' / 'signal.db').as_posix()}")
    artifacts_dir: Path = BACKEND_DIR / "data" / "artifacts"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    auto_seed: bool = True
    seed: int = 7
    # Optional LLM interpretation. Without a key the deterministic interpreter is used.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    # Minimum posts required before models are trained / predictions are served.
    min_posts_for_models: int = 80

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise provider URLs (postgres://, postgresql://) to the psycopg3 driver."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
