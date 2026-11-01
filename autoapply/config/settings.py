"""Application settings loaded from environment variables and .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration.

    Values are loaded from environment variables and a `.env` file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LinkedIn credentials
    linkedin_email: str = ""
    linkedin_password: str = ""

    # Naukri credentials
    naukri_email: str = ""
    naukri_password: str = ""

    # Instahyre credentials
    instahyre_email: str = ""
    instahyre_password: str = ""

    # AI
    gemini_api_key: str = ""

    # Runtime settings
    max_applications_per_day: int = 20
    headless_browser: bool = False
    dry_run: bool = True

    # Paths
    data_dir: str = "data"
    db_path: str = "data/autoapply.db"
