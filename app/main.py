"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from fastapi import FastAPI, Request
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
from app.workers import sms_worker, email_worker, followup_worker, promise_worker, drip_worker
from app.workers import health_snapshot_worker, chi_worker, burst_detection_worker, topic_worker
app.include_router(sms_worker.router, prefix="/workers", tags=["workers"])
app.include_router(followup_worker.router, prefix="/workers", tags=["workers"])
app.include_router(promise_worker.router, prefix="/workers", tags=["workers"])
app.include_router(email_worker.router, prefix="/workers/email", tags=["email-workers"])
app.include_router(health_snapshot_worker.router, prefix="/workers", tags=["workers"])
app.include_router(chi_worker.router, prefix="/workers", tags=["workers"])
app.include_router(burst_detection_worker.router, prefix="/workers", tags=["workers"])
app.include_router(topic_worker.router, prefix="/workers", tags=["workers"])
app.include_router(drip_worker.router, prefix="/workers", tags=["workers"])

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}


@app.post("/api/v1/telnyx/diagnostics")
async def telnyx_diagnostics():
    """Diagnose Telnyx connection/phone number/agent configuration for all tenants."""
    import httpx
    from fastapi.responses import JSONResponse as JR
    from sqlalchemy import select as sa_select
    from app.persistence.database import async_session_factory
    from app.persistence.models.tenant_sms_config import TenantSmsConfig
    from app.persistence.models.tenant_voice_config import TenantVoiceConfig
    from app.persistence.models.tenant import Tenant

    TELNYX_API = "https://api.telnyx.com/v2"
    results = []

    try:
        async with async_session_factory() as session:
            stmt = sa_select(Tenant, TenantSmsConfig, TenantVoiceConfig).outerjoin(
                TenantSmsConfig, Tenant.id == TenantSmsConfig.tenant_id
            ).outerjoin(
                TenantVoiceConfig, Tenant.id == TenantVoiceConfig.tenant_id
            )
            rows = (await session.execute(stmt)).all()

            for tenant, sms_cfg, voice_cfg in rows:
                diag = {
                    "tenant_id": tenant.id,
                    "tenant_name": tenant.name,
                    "phone": sms_cfg.telnyx_phone_number if sms_cfg else None,
                    "voice_phone": sms_cfg.voice_phone_number if sms_cfg else None,
                    "connection_id": sms_cfg.telnyx_connection_id if sms_cfg else None,
                    "messaging_profile_id": sms_cfg.telnyx_messaging_profile_id if sms_cfg else None,
                    "voice_enabled": sms_cfg.voice_enabled if sms_cfg else False,
                    "agent_id": voice_cfg.telnyx_agent_id if voice_cfg else None,
                    "voice_agent_id": voice_cfg.voice_agent_id if voice_cfg else None,
                    "api_key_present": bool(sms_cfg and sms_cfg.telnyx_api_key),
                    "telnyx_api_checks": {},
                }

                api_key = sms_cfg.telnyx_api_key if sms_cfg else None
                if not api_key:
                    diag["telnyx_api_checks"]["error"] = "No API key configured"
                    results.append(diag)
                    continue

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }

                async with httpx.AsyncClient(base_url=TELNYX_API, headers=headers, timeout=15.0) as client:
                    # Check API key validity
                    try:
                        resp = await client.get("/balance")
                        if resp.status_code == 200:
                            bal = resp.json().get("data", {})
                            diag["telnyx_api_checks"]["auth"] = "OK"
                            diag["telnyx_api_checks"]["balance"] = bal.get("balance")
                            diag["telnyx_api_checks"]["currency"] = bal.get("currency")
                        else:
                            diag["telnyx_api_checks"]["auth"] = f"FAILED ({resp.status_code}): {resp.text[:200]}"
                            results.append(diag)
                            continue
                    except Exception as e:
                        diag["telnyx_api_checks"]["auth"] = f"ERROR: {e}"
                        results.append(diag)
                        continue

                    # Check phone number configuration
                    if sms_cfg.telnyx_phone_number:
                        try:
                            phone = sms_cfg.telnyx_phone_number
                            resp = await client.get("/phone_numbers", params={
                                "filter[phone_number]": phone,
                            })
                            if resp.status_code == 200:
                                nums = resp.json().get("data", [])
                                if nums:
                                    num = nums[0]
                                    diag["telnyx_api_checks"]["phone_number"] = {
                                        "status": num.get("status"),
                                        "connection_id": num.get("connection_id"),
                                        "connection_name": num.get("connection_name"),
                                        "messaging_profile_id": num.get("messaging_profile_id"),
                                        "tags": num.get("tags"),
                                    }
                                else:
                                    diag["telnyx_api_checks"]["phone_number"] = "NOT FOUND in Telnyx account"
                            else:
                                diag["telnyx_api_checks"]["phone_number"] = f"API error: {resp.status_code}"
                        except Exception as e:
                            diag["telnyx_api_checks"]["phone_number"] = f"ERROR: {e}"

                    # Check connection details
                    conn_id = sms_cfg.telnyx_connection_id if sms_cfg else None
                    if conn_id:
                        try:
                            resp = await client.get(f"/connections/{conn_id}")
                            if resp.status_code == 200:
                                conn = resp.json().get("data", {})
                                diag["telnyx_api_checks"]["connection"] = {
                                    "id": conn.get("id"),
                                    "name": conn.get("connection_name"),
                                    "active": conn.get("active"),
                                    "webhook_event_url": conn.get("webhook_event_url"),
                                    "webhook_event_failover_url": conn.get("webhook_event_failover_url"),
                                    "record_type": conn.get("record_type"),
                                }
                            else:
                                diag["telnyx_api_checks"]["connection"] = f"NOT FOUND ({resp.status_code})"
                        except Exception as e:
                            diag["telnyx_api_checks"]["connection"] = f"ERROR: {e}"
                    else:
                        diag["telnyx_api_checks"]["connection"] = "No connection_id configured in DB"

                    # Check AI assistants (get details for each)
                    try:
                        resp = await client.get("/ai/assistants")
                        if resp.status_code == 200:
                            assistants = resp.json().get("data", [])
                            diag["telnyx_api_checks"]["ai_assistants"] = []
                            for a in assistants:
                                a_id = a.get("id")
                                detail = {"id": a_id, "name": a.get("name"), "model": a.get("model")}
                                # Get full details per assistant
                                try:
                                    dresp = await client.get(f"/ai/assistants/{a_id}")
                                    if dresp.status_code == 200:
                                        d = dresp.json().get("data", {})
                                        detail["phone_numbers"] = d.get("phone_numbers")
                                        detail["webhook_url"] = d.get("webhook_url")
                                        detail["status"] = d.get("status")
                                        detail["active"] = d.get("active")
                                        detail["greeting"] = (d.get("greeting") or "")[:80]
                                        detail["tools"] = [t.get("type") or t.get("name") for t in (d.get("tools") or [])]
                                    else:
                                        detail["detail_error"] = f"{dresp.status_code}"
                                except Exception as e2:
                                    detail["detail_error"] = str(e2)
                                diag["telnyx_api_checks"]["ai_assistants"].append(detail)
                        else:
                            diag["telnyx_api_checks"]["ai_assistants"] = f"API error: {resp.status_code} - {resp.text[:200]}"
                    except Exception as e:
                        diag["telnyx_api_checks"]["ai_assistants"] = f"ERROR: {e}"

                results.append(diag)

        return JR(content={"diagnostics": results})
    except Exception as e:
        import traceback
        return JR(status_code=500, content={"error": str(e), "traceback": traceback.format_exc()})


@app.api_route("/api/v1/telnyx/tools/get-classes", methods=["GET", "POST"])
async def get_classes_proxy(request: Request):
    """Proxy endpoint for Telnyx AI Assistant to fetch Jackrabbit class openings."""
    from fastapi.responses import JSONResponse as JR
    from sqlalchemy import select, text
    from app.infrastructure.jackrabbit_client import fetch_classes, format_classes_for_voice
    from app.persistence.database import AsyncSessionLocal
    from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig

    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        # 1. Explicit org_id takes priority
        org_id = body.get("org_id") or request.query_params.get("org_id")

        # 2. If no org_id, resolve from tenant_id via DB
        #    NOTE: ?tenant_id=X is the tenant_number (admin-assigned), which may
        #    differ from tenants.id (DB PK). Resolve via tenants table first.
        if not org_id:
            raw_tid = body.get("tenant_id") or request.query_params.get("tenant_id")
            if raw_tid:
                async with AsyncSessionLocal() as session:
                    await session.execute(text("SET app.current_tenant_id = ''"))
                    # Resolve tenant_number -> actual tenants.id
                    from app.persistence.models.tenant import Tenant
                    tid_int = int(raw_tid)
                    t_result = await session.execute(
                        select(Tenant.id).where(Tenant.tenant_number == str(tid_int))
                    )
                    resolved_id = t_result.scalar_one_or_none()
                    actual_tid = resolved_id if resolved_id is not None else tid_int
                    if resolved_id and resolved_id != tid_int:
                        logger.info(f"[get-classes] Resolved tenant_number={tid_int} -> tenants.id={resolved_id}")
                    result = await session.execute(
                        select(TenantCustomerServiceConfig.jackrabbit_org_id)
                        .where(TenantCustomerServiceConfig.tenant_id == actual_tid)
                    )
                    row = result.scalar_one_or_none()
                    if row:
                        org_id = row

        if not org_id:
            return JR(status_code=400, content={"error": "org_id or tenant_id required"})

        trimmed = await fetch_classes(str(org_id))
        spoken = format_classes_for_voice(trimmed)
        return JR(content={
            "classes": trimmed,
            "spoken_summary": spoken,
            "_instruction": (
                "IMPORTANT: You are speaking aloud on a phone call. "
                "Use the spoken_summary field to present class times. "
                "Do NOT use markdown, asterisks, bold, or bullet points. "
                "Do NOT reformat times. Say them exactly as shown."
            ),
        })
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

