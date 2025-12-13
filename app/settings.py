"""Application settings using Pydantic BaseSettings."""

import json
import os
import time
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

def _debug_log(location: str, message: str, data: dict, hypothesis_id: str = "A"):
    """Helper to safely write debug logs."""
    try:
        log_path = Path(".cursor/debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": location, "message": message, "data": data, "sessionId": "debug-session", "runId": "run1", "hypothesisId": hypothesis_id}) + "\n")
    except Exception:
        pass  # Silently fail if logging isn't possible


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

# #region agent log
_debug_log("settings.py:48", "Settings initialized", {"database_url_prefix": settings.database_url[:30] + "..." if len(settings.database_url) > 30 else settings.database_url, "has_cloud_sql_conn": settings.cloud_sql_instance_connection_name is not None, "gcp_project_id": settings.gcp_project_id, "environment": settings.environment})
# #endregion

