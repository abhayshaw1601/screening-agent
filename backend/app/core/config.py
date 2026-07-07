"""
config.py — Application settings loaded from environment variables.

Uses pydantic-settings to provide a single, validated Settings object.
All sensitive values (API keys, DB URLs) are read from .env or shell env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration.

    Reads from a ``.env`` file located in the ``backend/`` directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini / LLM -------------------------------------------------------
    gemini_api_key: str = ""
    google_api_key: str = ""

    # --- Database ------------------------------------------------------------
    database_url: str = "sqlite:///./screener.db"

    # --- App -----------------------------------------------------------------
    app_title: str = "PG AGI Screener API"
    max_interview_questions: int = 5


settings = Settings()
