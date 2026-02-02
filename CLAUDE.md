# CLAUDE.md — Project Context for Claude Code

## Project Overview

ChatterCheetah (ConvoPro) is a multi-tenant AI customer communication platform deployed on GCP Cloud Run. It provides SMS, voice, email, and web chat channels powered by Google Gemini LLM, with strict tenant isolation via PostgreSQL RLS.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI (async), SQLAlchemy 2.0 (async), Alembic
- **Frontend:** React + Vite (in `client/`)
- **Database:** Supabase PostgreSQL (asyncpg driver)
- **Cache:** Redis (Upstash, optional — `REDIS_ENABLED` flag)
- **LLM:** Google Gemini (`google-genai` SDK)
- **SMS/Voice:** Telnyx (primary), Twilio (legacy)
- **Email:** Gmail API (OAuth) + SendGrid (outbound)
- **Infra:** GCP Cloud Run, Cloud Tasks, Artifact Registry, Secret Manager
- **Package Manager:** uv (Python), npm (frontend)
- **Error Tracking:** Sentry

## Quick Reference

```bash
# Install & run backend
uv sync
uv run uvicorn app.main:app --reload  # http://localhost:8000

# Install & run frontend
cd client && npm install && npm run dev  # http://localhost:5173

# Local services (Postgres + Redis)
docker-compose up -d

# Run tests
uv run pytest

# Database migrations
uv run alembic upgrade head                          # apply all
uv run alembic revision --autogenerate -m "desc"     # create new
uv run alembic downgrade -1                          # rollback one

# Deploy to Cloud Run
gcloud run deploy chattercheatah \
  --source . \
  --region us-central1 \
  --project chatbots-466618
```

## GCP Deployment Details

- **Project:** `chatbots-466618`
- **Region:** `us-central1`
- **Service:** `chattercheatah` (note: typo in service name is intentional — this is the active service)
- **Active URL:** `https://chattercheatah-900139201687.us-central1.run.app`
- **Container Registry:** `us-central1-docker.pkg.dev/chatbots-466618/cloud-run-source-deploy/`

### Dockerfile Gotcha

The Dockerfile uses a multi-stage build with hatchling (`pyproject.toml` defines `[tool.hatch.build.targets.wheel] packages = ["app"]`). The builder stage must use `--no-install-project` with `uv sync` so the project isn't installed as a wheel into site-packages. Without this, the venv's stale copy takes import priority over the local `./app/` source.

### .gcloudignore

`.env` is intentionally NOT ignored — it's needed inside the Docker image for Cloud Run settings. `.env.local` and `.env.sync` remain ignored.

## Architecture

```
app/
├── api/routes/          # 38 route files, mounted at /api/v1
├── api/schemas/         # Pydantic request/response models
├── api/middleware.py     # Idempotency, rate limiting, tenant context
├── core/                # Auth (JWT), encryption (Fernet), tenant context (ContextVar)
├── domain/services/     # 42 business logic services
├── infrastructure/      # External integrations (Telnyx, Gmail, SendGrid, Redis, Cloud Tasks)
├── llm/                 # Gemini client, orchestrator, factory
├── persistence/
│   ├── database.py      # Async session + RLS tenant context
│   ├── models/          # 33 SQLAlchemy models
│   └── repositories/    # 25 repository classes
├── workers/             # Cloud Tasks background jobs (SMS, email, followup, etc.)
├── main.py              # FastAPI app entry point
└── settings.py          # Pydantic settings from env vars
```

### Route Organization

All routes are included via `app/api/routes/__init__.py`. Key prefixes:
- `/telnyx` — Telnyx webhooks (voice AI, SMS, tool endpoints)
- `/sms` — Twilio SMS webhooks
- `/voice` — Twilio voice webhooks
- `/admin` — Admin dashboard endpoints
- `/tenants` — Tenant management
- `/chat` — Web chat widget API

The telnyx router is at `prefix="/telnyx"`, so routes defined as `@router.post("/tools/send-link")` are accessible at `/api/v1/telnyx/tools/send-link`.

**SPA catch-all:** `main.py` has `@app.get("/{full_path:path}")` that serves the React app for all unmatched GET requests. This means GET API routes on subrouters can be swallowed — prefer POST for webhook/tool endpoints.

### Get-classes proxy endpoint

`POST /api/v1/telnyx/tools/get-classes` is defined directly on `app` in `main.py` (not on the telnyx router). It proxies the Jackrabbit OpeningsJson API, filters out classes with no openings, and trims each class to essential fields (id, name, location, days, times, openings, fee).

## Multi-Tenancy

- **Database:** PostgreSQL RLS policies on all tenant-owned tables. `app.current_tenant_id` session variable set per request in `database.py`.
- **Application:** Python `ContextVar` in `core/tenant_context.py` for async-safe tenant tracking.
- **Auth:** JWT tokens carry `user_id`, `tenant_id`, `role`. Global admins (no tenant_id) can impersonate via `X-Tenant-Id` header.
- **Roles:** `admin` (global), `tenant_admin`, `user`

### Per-Tenant Config Tables

Each tenant has 1:1 config rows:
- `tenant_sms_configs` — Telnyx/Twilio phone, API keys, messaging profile
- `tenant_voice_configs` — Telnyx agent ID, handoff mode, transfer number
- `tenant_email_configs` — Gmail OAuth, SendGrid settings
- `tenant_widget_configs` — Chat widget customization
- `tenant_business_profiles` — Business info, scraped website data
- `tenant_customer_service_configs` — Jackrabbit API keys, Zapier integration

## Key Conventions

- **Async everywhere:** All DB ops and external calls use async/await
- **Repository pattern:** All data access goes through `app/persistence/repositories/`
- **Service layer:** Business logic lives in `app/domain/services/`
- **Dependency injection:** FastAPI `Depends()` for auth, DB sessions, tenant resolution
- **Field encryption:** Sensitive columns (API keys) encrypted with Fernet via `core/encryption.py`
- **Phone normalization:** E.164 format, use `core/phone.py` utilities
- **Naming:** snake_case files/functions, PascalCase classes, UPPER_SNAKE_CASE constants
- **Timestamps:** UTC naive datetimes (`datetime.utcnow()`) for `created_at`/`updated_at`

## Environment Variables

Required (see `.env.example`):
- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET_KEY` — JWT signing
- `GEMINI_API_KEY` — Google AI
- `FIELD_ENCRYPTION_KEY` — Fernet key for DB field encryption

Production secrets are in GCP Secret Manager, mounted as env vars in Cloud Run.

## Current Tenant Setup

- **Tenant 1 (CP Marketing):** Production tenant, `telnyx_agent_id` cleared
- **Tenant 2 (testing agency):** Test tenant, phone +12817679141, Telnyx agent `assistant-109f3350-874f-4770-87d4-737450280441`, Jackrabbit integration (OrgID 545911)
- **Tenant 3 (BSS Cypress-Spring):** Production tenant

## New Tenant Onboarding

### Per-Tenant Integrations

#### 1. Telnyx (SMS + Voice AI) — Primary
- **Config tables:** `tenant_sms_configs`, `tenant_voice_configs`
- **Keys needed:** `telnyx_api_key`, `telnyx_messaging_profile_id`, `telnyx_connection_id`, `telnyx_phone_number`, `telnyx_agent_id`
- **Setup steps:**
  1. Create/assign Telnyx API v2 key
  2. Create Messaging Profile and assign phone number
  3. Configure 10DLC campaign and brand (required for US SMS)
  4. Create Telnyx AI Assistant with tenant-specific system prompt (see `docs/BSS_VOICE_AGENT_PROMPT_COMBINED.md` for an example)
  5. Set webhook URLs in Telnyx portal:
     - Inbound SMS → `POST /api/v1/telnyx/sms/inbound`
     - SMS Status → `POST /api/v1/telnyx/sms/status`
     - Call Complete → `POST /api/v1/telnyx/ai-call-complete`
     - Call Progress → `POST /api/v1/telnyx/call-progress`
  6. Configure AI Agent tool endpoints:
     - Send Link → `POST /api/v1/telnyx/tools/send-link`
     - Get Classes → `POST /api/v1/telnyx/tools/get-classes`
- **Signature verification:** `telnyx-signature-ed25519` (ED25519), `telnyx-timestamp` (must be within 5 min)

#### 2. Twilio (Legacy/Alternative)
- **Config table:** `tenant_sms_configs`
- **Keys needed:** `twilio_account_sid`, `twilio_auth_token`, `twilio_phone_number`
- **Webhook URLs:** `/api/v1/sms/inbound`, `/api/v1/sms/status`, `/api/v1/voice/inbound`

#### 3. Gmail (OAuth Email)
- **Config table:** `tenant_email_configs`
- **Keys stored:** `gmail_email`, `gmail_refresh_token`, `gmail_access_token`
- **Setup:** Tenant clicks "Connect Gmail" in settings → OAuth flow → tokens stored automatically. Pub/Sub watch auto-renews every 7 days.
- **Webhook:** Gmail push notifications arrive at `POST /api/v1/email/pubsub` via Google Pub/Sub

#### 4. SendGrid (Outbound + Inbound Parse Email)
- **Config table:** `tenant_email_configs`
- **Keys needed:** `sendgrid_api_key`, `sendgrid_from_email`, `sendgrid_parse_address`, `sendgrid_webhook_secret`
- **Webhook:** Inbound email → `POST /api/v1/sendgrid/inbound`

#### 5. Zapier + Jackrabbit (Customer Service CRM)
- **Config table:** `tenant_customer_service_configs`
- **Keys needed:** `zapier_webhook_url`, `zapier_callback_secret`, `jackrabbit_api_key_1`, `jackrabbit_api_key_2`
- **Setup:**
  1. Create Zapier Zaps with "Catch Hook" triggers (customer lookup + query)
  2. Configure Jackrabbit actions in Zapier
  3. Store webhook URLs and callback secret in config
- **Callback webhooks:** `/api/v1/zapier/callback`, `/api/v1/zapier/customer-update`

#### 6. Business Profile + Widget
- **Config tables:** `tenant_business_profiles`, `tenant_widget_configs`
- **Data:** business name, website URL, phone, email, widget styling/customization
- **Widget assets:** stored in GCS at `tenants/{tenant_id}/widget-assets/`

### Global Integrations (configured once, shared across all tenants)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection |
| `JWT_SECRET_KEY` | JWT token signing |
| `FIELD_ENCRYPTION_KEY` | Fernet encryption of API keys in DB |
| `GEMINI_API_KEY` | Google Gemini LLM |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` | Shared Gmail OAuth app |
| `GMAIL_PUBSUB_TOPIC` / `GMAIL_PUBSUB_AUTH_TOKEN` | Gmail push notifications |
| `SENDGRID_API_KEY` / `SENDGRID_FROM_EMAIL` | SendGrid fallback (optional) |
| `TRESTLE_API_KEY` | Trestle IQ reverse phone lookup (optional) |
| `SCRAPINGBEE_API_KEY` | Website scraping fallback (optional) |
| `SENTRY_DSN` | Error tracking (optional) |
| `GCP_PROJECT_ID` / `GCP_REGION` | Google Cloud project |
| `GCS_WIDGET_ASSETS_BUCKET` | Widget asset storage bucket |
| `CLOUD_TASKS_QUEUE_NAME` / `CLOUD_TASKS_WORKER_URL` | Background task queue |
| `CLOUD_TASKS_EMAIL_WORKER_URL` | Email worker endpoint |
| `REDIS_ENABLED` / `REDIS_URL` | Redis caching (optional, currently off) |

### All Webhook Endpoints (unauthenticated/public)

| Path | Source | Purpose |
|------|--------|---------|
| `/api/v1/telnyx/sms/inbound` | Telnyx | Inbound SMS |
| `/api/v1/telnyx/sms/status` | Telnyx | SMS delivery status |
| `/api/v1/telnyx/ai-call-complete` | Telnyx | Voice call complete + transcript |
| `/api/v1/telnyx/call-progress` | Telnyx | Call state updates |
| `/api/v1/telnyx/tools/send-link` | Telnyx AI Agent | Send SMS registration link |
| `/api/v1/telnyx/tools/get-classes` | Telnyx AI Agent | Jackrabbit class proxy |
| `/api/v1/sms/inbound` | Twilio | Inbound SMS |
| `/api/v1/sms/status` | Twilio | SMS delivery status |
| `/api/v1/voice/inbound` | Twilio | Inbound voice call |
| `/api/v1/email/pubsub` | Google Pub/Sub | Gmail push notifications |
| `/api/v1/sendgrid/inbound` | SendGrid | Inbound email parse |
| `/api/v1/zapier/callback` | Zapier | Async lookup callback |
| `/api/v1/zapier/customer-update` | Zapier | Cache invalidation |

### Minimum Onboarding Checklist

1. Create tenant record in DB (via admin API or direct insert)
2. Set up Telnyx: API key, messaging profile, phone number, AI assistant with custom prompt, all webhooks
3. Fill in `tenant_business_profiles` (business name, website, phone, email)
4. Connect Gmail via OAuth (if using email channel)
5. Set up Zapier + Jackrabbit integration (if applicable)
6. Configure `tenant_widget_configs` for chat widget styling
7. Optional: SendGrid for outbound email, Twilio as SMS/voice fallback, Google Calendar
