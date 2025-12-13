"""Application settings using Pydantic BaseSettings."""

import os
import re

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_async_database_url() -> str:
    """Get database URL converted for asyncpg driver."""
    url = os.environ.get("DATABASE_URL", "")
    # Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # asyncpg doesn't support sslmode, it uses ssl parameter
    # Remove sslmode parameter as Replit's internal DB doesn't need SSL
    if "sslmode=" in url:
        url = re.sub(r'[?&]sslmode=[^&]*', '', url)
        # Clean up any leftover ? or & at the end
        url = url.rstrip('?&')
    return url


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GCP Configuration (optional for local dev)
    gcp_project_id: str = "local-development"
    gcp_region: str = "us-central1"

    # Cloud SQL (Postgres)
    database_url: str = ""
    cloud_sql_instance_connection_name: str | None = None
    cloud_sql_database_name: str = "chattercheatah"

    # Redis (optional)
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_enabled: bool = False  # Disable Redis by default for dev

    # JWT
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # LLM (Gemini) - optional for basic functionality
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"  # Using Flash 2.0 (Flash 2.5 not yet available, will update when released)
    
    # Chat guardrails
    chat_max_turns: int = 20
    chat_timeout_seconds: int = 300
    chat_follow_up_nudge_turn: int = 3

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Idempotency
    idempotency_ttl_seconds: int = 3600

    # Twilio (SMS)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_webhook_url_base: str | None = None  # Base URL for webhook endpoints

    # Cloud Tasks
    cloud_tasks_queue_name: str = "sms-processing"
    cloud_tasks_location: str = "us-central1"
    cloud_tasks_worker_url: str | None = None  # URL for worker endpoint

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

# Import debug_log after settings is created to avoid circular import
from app.core.debug import debug_log

# #region agent log
debug_log("settings.py:48", "Settings initialized", {"database_url_prefix": settings.database_url[:30] + "..." if len(settings.database_url) > 30 else settings.database_url, "has_cloud_sql_conn": settings.cloud_sql_instance_connection_name is not None, "gcp_project_id": settings.gcp_project_id, "environment": settings.environment})
# #endregion

