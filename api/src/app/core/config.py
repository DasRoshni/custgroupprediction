"""Application configuration via Pydantic Settings (env-driven, 12-factor)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config. Values come from env vars (or `.env` for local dev)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        protected_namespaces=(),
    )

    app_name: str = "customer-group-predictor"
    environment: str = Field(default="dev", description="dev|staging|prod")
    log_level: str = "INFO"

    # Model artifact location. Typed as `str` (not Path) because the value
    # can be either a local filesystem path OR a gs:// URI — Path() would
    # normalize "gs://bucket/key" to "gs:/bucket/key" (single slash) and break
    # the GCS loader's prefix check.
    model_path: str = Field(
        default=str(Path(__file__).resolve().parents[4] / "ml" / "artifacts" / "model.joblib")
    )
    metadata_path: str = Field(
        default=str(Path(__file__).resolve().parents[4] / "ml" / "artifacts" / "metadata.json")
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Toggles
    enable_metrics: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
