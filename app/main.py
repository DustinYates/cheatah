"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.middleware import IdempotencyMiddleware
from app.api.routes import api_router
from app.core.debug import debug_log
from app.infrastructure.redis import redis_client
from app.logging_config import setup_logging
from app.settings import settings

# Setup logging
setup_logging()

# Initialize Sentry for error tracking
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_traces_sample_rate,
        enable_tracing=True,
        # Capture 100% of errors
        sample_rate=1.0,
        # Add useful context
        send_default_pii=False,  # Don't send personally identifiable info
        # Integrations are auto-detected for FastAPI, SQLAlchemy, etc.
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # #region agent log
    debug_log("main.py:22", "Application startup - connecting Redis", {}, "C")
    # #endregion
    # Startup
    try:
        await redis_client.connect()
        # #region agent log
        debug_log("main.py:27", "Redis connected successfully", {}, "C")
        # #endregion
    except Exception as e:
        # #region agent log
        debug_log("main.py:31", "Redis connection error", {"error_type": type(e).__name__, "error_message": str(e)}, "C")
        # #endregion
        raise
    yield
    # Shutdown
    await redis_client.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Chatter Cheetah API",
    description="Multi-tenant AI customer communication platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add idempotency middleware
app.add_middleware(IdempotencyMiddleware)

# Include API routes
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Include worker routes (for Cloud Tasks)
from app.workers import sms_worker, email_worker, followup_worker, promise_worker
app.include_router(sms_worker.router, prefix="/workers", tags=["workers"])
app.include_router(followup_worker.router, prefix="/workers", tags=["workers"])
app.include_router(promise_worker.router, prefix="/workers", tags=["workers"])
app.include_router(email_worker.router, prefix="/workers/email", tags=["email-workers"])

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}


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
        "message": "Chatter Cheetah API",
        "version": "0.1.0",
        "docs": "/docs",
    }

