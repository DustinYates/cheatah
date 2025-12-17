"""FastAPI application entry point."""

from contextlib import asynccontextmanager

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
from app.workers import sms_worker
app.include_router(sms_worker.router, prefix="/workers", tags=["workers"])

# Serve static files (chat widget)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Chatter Cheetah API",
        "version": "0.1.0",
        "docs": "/docs",
        "admin_dashboard": "/static/admin-dashboard.html",
    }


@app.get("/admin")
async def admin_dashboard_redirect():
    """Redirect to admin dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/admin-dashboard.html")

