# Chatter Cheetah

Multi-tenant AI customer communication platform built on GCP.

## Phase 0

This is the foundational backend architecture phase, focusing on:
- Multi-tenant architecture with strict tenant isolation
- Core persistence (Tenants, Users, Conversations, Messages, Leads, Prompts)
- Prompt system with global base and tenant overrides
- LLM abstraction layer (Gemini 2.5 Flash)
- Redis caching and idempotency
- Analytics event hooks

## Twilio Subaccount Plan

Phase 1 now assumes every tenant is mapped to a Twilio subaccount under the global admin account so that inbound/outbound chat, SMS, voice, and eventually email bots are isolated by `AccountSid` instead of only by shared phone numbers. The detailed implementation plan is tracked in `phase_1_mvp_ai_receptionist_80f03ecc.plan.md`, but the summary is:

1. Provision a Twilio subaccount per tenant and persist its SID/credentials in the tenant profile.
2. Map incoming webhooks to tenants using the subaccount `AccountSid` (with fallbacks to configured numbers) before creating conversations or leads.
3. Use the tenant-specific credentials for outbound interactions so chat/SMS/voice requests stay within that tenant’s sandbox.

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: Cloud SQL (Postgres)
- **Cache**: Redis (MemoryStore)
- **Package Manager**: uv
- **Deployment**: Cloud Run
- **LLM**: Gemini 2.5 Flash via Google Generative AI

## Setup (Backend)

### Prerequisites

- Python 3.11+
- uv (https://github.com/astral-sh/uv)
- Docker and Docker Compose (for local services)

### Installation (API)

1. Clone the repository
2. Install dependencies:
   ```bash
   uv sync
   ```

3. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```

   **Important:** For debugging scripts and local development, always use the production database connection string. Local database connections may point to different databases or stale data. Use the production `DATABASE_URL` from GCP Secret Manager.

4. Start local services (Postgres + Redis):
   ```bash
   docker-compose up -d
   ```

5. Run migrations:
   ```bash
   uv run alembic upgrade head
   ```

6. Start the development server:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

### Environment variables

Set the following in `.env`:

| Variable | Description | Example |
| --- | --- | --- |
| `DATABASE_URL` | Postgres URL (asyncpg) | `postgresql+asyncpg://user:pass@localhost:5432/chattercheatah` |

**Note:** When running debug scripts or local development tools, always use the production database connection string from GCP Secret Manager. Local `.env` files may point to different databases or contain stale data, which can cause confusion when debugging production issues.

| `REDIS_URL` | Redis connection (optional for dev) | `redis://localhost:6379/0` |
| `REDIS_ENABLED` | Toggle Redis use | `false` |
| `JWT_SECRET_KEY` | JWT signing key | `change-me` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `GEMINI_API_KEY` | Google AI key | `...` |
| `GEMINI_MODEL` | Gemini model | `gemini-3-flash-preview` |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | SMS credentials (optional) | `...` |
| `CLOUD_TASKS_WORKER_URL` | Cloud Tasks worker endpoint (prod) | `https://.../workers/sms` |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID | `...` |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret | `...` |
| `GMAIL_PUBSUB_TOPIC` | Gmail push notifications topic | `projects/.../topics/gmail-push` |
| `CLOUD_TASKS_EMAIL_WORKER_URL` | Email worker endpoint (prod) | `https://.../workers/email` |

The API will still start with Redis disabled or LLM keys missing; related features will be no-ops.

## Project Structure

- `app/` - Main application code
  - `api/` - FastAPI routes and middleware
  - `domain/` - Domain services and models
  - `persistence/` - Database models and repositories
  - `llm/` - LLM abstraction layer
  - `infrastructure/` - Redis, Pub/Sub, Analytics
  - `core/` - Auth, tenant context, idempotency
- `alembic/` - Database migrations
- `tests/` - Test suite
- `notebooks/` - Jupyter notebooks for analysis (Vertex AI Workbench)
- `scripts/` - Python analysis scripts
- `client/` - React frontend (Vite)

## Frontend (Vite React)

```bash
cd client
npm install
npm run dev   # http://localhost:5173
```

Configure API base in `client/.env`:
```
VITE_API_URL=http://localhost:8000/api/v1
```

## Development Tasks

### Running Tests

```bash
uv run pytest
```

Frontend tests:
```bash
cd client
npm run test
```

### Database Migrations

Create a new migration:
```bash
uv run alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
uv run alembic upgrade head
```

## Deployment

The application is designed to run on:
- **Cloud Run** - Main FastAPI application
- **Vertex AI Workbench** - Notebooks and analysis scripts

See deployment documentation for GCP setup instructions.

## Deployment Reference

**Project Structure:**
- Backend: `~/Desktop/chattercheetah/app`
- Frontend: `~/Desktop/chattercheetah/client`

**Cloud Run Services:**
- Backend: `chattercheatah` → https://chattercheatah-900139201687.us-central1.run.app
- Frontend: `chattercheatah-frontend` → https://chattercheatah-frontend-900139201687.us-central1.run.app

**Database:**
- Cloud SQL Instance: `chattercheatah-db` (PostgreSQL 15) in `us-central1-c`
- Database Name: `chattercheatah`

**Deploy Commands:**
```bash
# Frontend
cd ~/Desktop/chattercheetah/client
npm run build
gcloud run deploy chattercheatah-frontend --source . --region us-central1 --project chatbots-466618 --allow-unauthenticated

# Backend
cd ~/Desktop/chattercheetah
gcloud run deploy chattercheatah --source . --region us-central1 --project chatbots-466618
```

## Communication Channels

### Web Chat
- Embedded chat widget for websites
- Real-time AI-powered responses
- Lead capture and conversation history

### SMS
- Twilio-based SMS handling
- Compliance handling (STOP, HELP, etc.)
- Business hours support

### Voice
- AI receptionist for inbound calls
- Call recording and summarization
- Handoff to human agents

### Email (NEW)
- Gmail-based email responder
- OAuth 2.0 tenant authentication
- Thread-aware AI responses
- See `docs/EMAIL_RESPONDER_SETUP.md` for setup

## Additional Docs

- `DEVELOPMENT.md` — sync workflow between local and GCP Vertex AI Workbench
- `DEPLOYMENT.md` — Cloud Run deployment, secrets, and troubleshooting
- `docs/EMAIL_RESPONDER_SETUP.md` — Gmail email responder configuration
- `docs/VOICE_ASSISTANT_ROADMAP.md` — Voice assistant implementation plan
- `docs/tenant_onboarding.md` — tenant onboarding runbook (repeatable process + examples)
- `docs/config_matrix.md` — configuration/secrets matrix (global vs per-tenant)
