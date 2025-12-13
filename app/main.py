"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import IdempotencyMiddleware
from app.api.routes import api_router
from app.infrastructure.redis import redis_client
from app.logging_config import setup_logging
from app.settings import settings

# Setup logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    import json
    import time
    # #region agent log
    with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
        f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "main.py:22", "message": "Application startup - connecting Redis", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "C"}) + "\n")
    # #endregion
    # Startup
    try:
        await redis_client.connect()
        # #region agent log
        with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "main.py:27", "message": "Redis connected successfully", "data": {}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "C"}) + "\n")
        # #endregion
    except Exception as e:
        # #region agent log
        with open("/Users/dustinyates/Desktop/chattercheatah/.cursor/debug.log", "a") as f:
            f.write(json.dumps({"timestamp": int(time.time() * 1000), "location": "main.py:31", "message": "Redis connection error", "data": {"error_type": type(e).__name__, "error_message": str(e)}, "sessionId": "debug-session", "runId": "run1", "hypothesisId": "C"}) + "\n")
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
    }

