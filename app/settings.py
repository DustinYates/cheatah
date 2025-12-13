"""Application settings using Pydantic BaseSettings."""

import json
import time
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GCP Configuration
    gcp_project_id: str
    gcp_region: str = "us-central1"

    # Cloud SQL (Postgres)
    database_url: str
    cloud_sql_instance_connection_name: str | None = None
    cloud_sql_database_name: str = "chattercheatah"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_host: str = "localhost"
    redis_port: int = 6379

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # LLM (Gemini)
    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash-exp"

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Idempotency
    idempotency_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()

# #region agent log
with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
    f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "settings.py:48", "message": "Settings initialized", "data": {"database_url_prefix": settings.database_url[:30] + "..." if len(settings.database_url) > 30 else settings.database_url, "has_cloud_sql_conn": settings.cloud_sql_instance_connection_name is not None, "gcp_project_id": settings.gcp_project_id, "environment": settings.environment}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "A"}) + "\n")
# #endregion

