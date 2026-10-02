from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")
    database_url: str = "sqlite:///./cybershield-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-this-development-secret-before-deployment"
    app_url: str = "http://localhost:5173"
    environment: str = "development"
    cookie_secure: bool = False
    allow_public_registration: bool = True
    ai_api_key: str | None = None
    ai_api_base: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    webhook_encryption_key: str | None = None
    report_dir: str = "/tmp/cybershield-reports"
    evidence_storage_path: str = "/var/lib/cybershield/evidence"
    scan_timeout_seconds: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
