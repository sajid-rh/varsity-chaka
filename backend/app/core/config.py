"""Application settings, read from environment variables or the .env file.

No credentials are hardcoded here. Values come from `.env` at the repo root
(never committed). See `.env.example` for the variable names.
"""
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels above "core"
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "varsity_chaka"
    mysql_user: str
    mysql_password: str

    secret_key: str
    access_token_expire_minutes: int = 60
    app_env: str = "development"

    osrm_base_url: str = "http://127.0.0.1:5000"
    app_base_url: str = "http://127.0.0.1:8000"  # used to build links in emails
    # Private folder for uploaded documents. It is never served as static files.
    upload_dir: Path = REPO_ROOT / "backend" / "uploads"
    cookie_secure: bool = False  # set COOKIE_SECURE=true when the site is served over HTTPS

    # Used only by `python -m app.seed`. Optional, so the app starts without them.
    seed_super_admin_email: str | None = None
    seed_admin_password: str | None = None
    seed_fuel_price_per_litre: Decimal | None = None
    seed_max_rate_per_km: Decimal | None = None

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds MYSQL_ROOT_PASSWORD, used only by Docker
    )

    @property
    def database_url(self) -> str:
        # quote_plus keeps special characters in the password from breaking the URL
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
