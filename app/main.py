"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

from app.api.middleware import (
    IdempotencyMiddleware,
    TenantRateLimitMiddleware,
    SecurityHeadersMiddleware,
    RequestContextMiddleware,
)
from app.api.routes import api_router
from app.infrastructure.redis import redis_client
from app.logging_config import setup_logging
from app.settings import settings

# Setup logging
setup_logging()

# Initialize Sentry for error tracking with explicit integrations
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_traces_sample_rate,
        enable_tracing=True,
        sample_rate=1.0,
        send_default_pii=False,
        integrations=[
            # FastAPI/Starlette for request handling
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            # SQLAlchemy for database error tracking
            SqlalchemyIntegration(),
            # HTTPX for external API call tracking (Gemini, Twilio, etc.)
            HttpxIntegration(),
            # Logging integration to capture log messages as breadcrumbs
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        # Add before_send hook for context enrichment
        before_send=_enrich_sentry_event,
    )


def _enrich_sentry_event(event, hint):
    """Enrich Sentry events with tenant and request context."""
    from app.core.tenant_context import get_tenant_context
    from app.api.middleware import get_current_request_id

    # Add tenant context
    tenant_id = get_tenant_context()
    if tenant_id:
        event.setdefault("tags", {})["tenant_id"] = str(tenant_id)
        event.setdefault("user", {})["tenant_id"] = tenant_id

    # Add request ID for correlation
    request_id = get_current_request_id()
    if request_id:
        event.setdefault("tags", {})["request_id"] = request_id

    return event

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Redis connection error: {e}", exc_info=True)
        raise
    yield
    # Shutdown
    await redis_client.disconnect()


# Create FastAPI app
app = FastAPI(
    title="ConvoPro API",
    description="Multi-tenant AI customer communication platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure allowed CORS origins
# The chat widget is embedded on customer websites, so we need to allow all origins
# for widget endpoints. Authentication is handled via API key, not CORS.
ALLOWED_ORIGINS = ["*"]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Must be False when allow_origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Id", "Idempotency-Key", "X-Widget-Api-Key"],
)

# Add idempotency middleware
app.add_middleware(IdempotencyMiddleware)

# Add per-tenant rate limiting middleware
app.add_middleware(TenantRateLimitMiddleware)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add request context middleware (runs first, wraps all other middleware)
# Must be added last so it executes first in the middleware chain
app.add_middleware(RequestContextMiddleware)

# Include API routes
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Include worker routes (for Cloud Tasks)
from app.workers import sms_worker, email_worker, followup_worker, promise_worker
from app.workers import health_snapshot_worker, chi_worker, burst_detection_worker
app.include_router(sms_worker.router, prefix="/workers", tags=["workers"])
app.include_router(followup_worker.router, prefix="/workers", tags=["workers"])
app.include_router(promise_worker.router, prefix="/workers", tags=["workers"])
app.include_router(email_worker.router, prefix="/workers/email", tags=["email-workers"])
app.include_router(health_snapshot_worker.router, prefix="/workers", tags=["workers"])
app.include_router(chi_worker.router, prefix="/workers", tags=["workers"])
app.include_router(burst_detection_worker.router, prefix="/workers", tags=["workers"])

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}


@app.post("/api/v1/telnyx/tools/get-classes")
async def get_classes_proxy():
    """Proxy endpoint for Telnyx AI Assistant to fetch Jackrabbit class openings."""
    import httpx
    from fastapi.responses import JSONResponse as JR

    jackrabbit_url = "https://app.jackrabbitclass.com/jr3.0/Openings/OpeningsJson"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(jackrabbit_url, params={"OrgID": "545911"})
            resp.raise_for_status()
            raw = resp.json()
            rows = raw.get("rows", []) if isinstance(raw, dict) else raw

        trimmed = []
        for c in rows:
            openings = c.get("openings", {})
            calc = openings.get("calculated_openings", 0)
            if calc <= 0:
                continue
            trimmed.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "location": c.get("location_name"),
                "days": c.get("meeting_days"),
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time"),
                "openings": calc,
                "fee": (c.get("tuition") or {}).get("fee"),
            })

        return JR(content={"classes": trimmed})
    except Exception as e:
        return JR(status_code=500, content={"error": str(e)})


# Serve static files (chat widget and client app)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve React client app assets
client_dir = static_dir / "client"
if client_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(client_dir / "assets")), name="assets")


# Serve React app for all non-API routes (must be last)
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    """Serve React app for client-side routing."""
    # Serve index.html for all routes (React Router will handle)
    client_dir = Path(__file__).parent.parent / "static" / "client"
    index_file = client_dir / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "message": "ConvoPro API",
        "version": "0.1.0",
        "docs": "/docs",
    }

