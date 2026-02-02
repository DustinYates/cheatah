"""Application settings using Pydantic BaseSettings."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file from project root before any environment variables are read
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

def get_async_database_url() -> str:
    """Get database URL converted for asyncpg driver."""
    url = os.environ.get("DATABASE_URL", "")
    # Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # Handle SSL for different environments
    # Supabase uses sslmode=require, asyncpg needs ssl=require
    if "sslmode=require" in url:
        url = url.replace("sslmode=require", "ssl=require")
    elif "sslmode=" in url:
        # Remove other sslmode parameters (for local/internal DBs)
        url = re.sub(r'[?&]sslmode=[^&]*', '', url)
        url = url.rstrip('?&')
    return url


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GCP Configuration (optional for local dev)
    gcp_project_id: str = "local-development"
    gcp_region: str = "us-central1"
    gcs_widget_assets_bucket: str = ""  # GCS bucket for widget assets (icons, images)

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
    jwt_access_token_expire_minutes: int = 720

    # Field-level encryption (for API keys, tokens, secrets in database)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    field_encryption_key: str | None = None

    # LLM (Gemini) - optional for basic functionality
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"  # Using Gemini 3 Flash for faster, higher quality voice responses

    # ScrapingBee API (for scraping sites with bot protection)
    scrapingbee_api_key: str = ""
    
    # Chat guardrails
    chat_max_turns: int = 100
    chat_timeout_seconds: int = 2700  # 45 minutes (increased from 15 minutes)
    chat_follow_up_nudge_turn: int = 3
    chat_max_tokens: int = 8000  # Max tokens for LLM chat responses

    # Sentry Error Tracking
    sentry_dsn: str = ""  # Get from https://sentry.io
    sentry_traces_sample_rate: float = 0.1  # 10% of transactions for performance monitoring

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    sms_dedup_disabled: bool = False  # Set to True to disable SMS deduplication (for testing)
    api_v1_prefix: str = "/api/v1"
    api_base_url: str = ""  # Base URL for embed code generation (e.g., https://chattercheatah-900139201687.us-central1.run.app)

    # Idempotency
    idempotency_ttl_seconds: int = 3600

    # Telnyx (Voice AI)
    telnyx_api_key: str | None = None  # Global Telnyx API key for AI conversation fetching

    # Twilio (SMS)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_webhook_url_base: str | None = None  # Base URL for webhook endpoints

    # Cloud Tasks
    cloud_tasks_queue_name: str = "sms-processing"
    cloud_tasks_location: str = "us-central1"
    cloud_tasks_worker_url: str | None = None  # URL for worker endpoint
    cloud_tasks_email_worker_url: str | None = None  # URL for email worker endpoint

    # Gmail OAuth (for email responder)
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_pubsub_topic: str | None = None  # e.g., projects/{project}/topics/{topic}
    gmail_oauth_redirect_uri: str | None = None  # OAuth callback URL
    gmail_pubsub_auth_token: str | None = None  # Shared secret for Pub/Sub push verification
    frontend_url: str | None = None  # Frontend URL for OAuth redirects

    # Google Calendar OAuth (for meeting scheduling)
    # Falls back to gmail_client_id/gmail_client_secret if not set
    google_calendar_client_id: str | None = None
    google_calendar_client_secret: str | None = None
    google_calendar_oauth_redirect_uri: str | None = None

    # SendGrid (Email sending)
    sendgrid_api_key: str | None = None
    sendgrid_from_email: str = "noreply@yourdomain.com"  # Default from email
    # SendGrid Inbound Parse (alternative to Gmail OAuth)
    sendgrid_inbound_parse_domain: str = ""  # e.g., "parse.yourdomain.com"
    sendgrid_default_webhook_secret: str | None = None  # Fallback secret if tenant-specific not set

    # Trestle IQ (reverse phone lookup for form pre-fill)
    trestle_api_key: str | None = None

    # Customer Service / Zapier Integration
    zapier_default_callback_timeout: int = 30  # Default timeout waiting for Zapier callback
    zapier_signature_header: str = "X-Zapier-Signature"  # Header for HMAC signature
    customer_service_cache_ttl_seconds: int = 3600  # 1 hour cache for Jackrabbit customers
    customer_lookup_retry_count: int = 2  # Number of retries for failed lookups

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
