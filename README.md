# Chatter Cheatah

Multi-tenant AI customer communication platform built on GCP.

## Overview

AI-powered customer communication platform supporting:
- Multi-tenant architecture with strict tenant isolation
- Web chat, SMS, voice, and email channels
- Prompt system with global base and tenant overrides
- LLM abstraction layer (Gemini 2.5 Flash)
- Redis caching and idempotency
- Lead capture and analytics

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis (Upstash)
- **Package Manager**: uv
- **Deployment**: Cloud Run
- **LLM**: Gemini 2.5 Flash via Google Generative AI
- **SMS/Voice**: Telnyx

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

### Environment Variables

Set the following in `.env`:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Supabase Postgres URL (asyncpg) |
| `REDIS_URL` | Redis connection URL |
| `REDIS_ENABLED` | Toggle Redis use (`true`/`false`) |
| `JWT_SECRET_KEY` | JWT signing key |
| `GEMINI_API_KEY` | Google AI API key |
| `GEMINI_MODEL` | Gemini model (e.g., `gemini-2.5-flash-preview-05-20`) |
| `TELNYX_API_KEY` | Telnyx API key for SMS/Voice |
| `GMAIL_CLIENT_ID` | Gmail OAuth client ID |
| `GMAIL_CLIENT_SECRET` | Gmail OAuth client secret |

## Project Structure

- `app/` - Main application code
  - `api/` - FastAPI routes and middleware
  - `domain/` - Domain services and models
  - `persistence/` - Database models and repositories
  - `llm/` - LLM abstraction layer
  - `infrastructure/` - Redis, Pub/Sub, Analytics
  - `core/` - Auth, tenant context, idempotency
  - `workers/` - Background workers (SMS, email)
  - `utils/` - Utility functions
- `alembic/` - Database migrations
- `tests/` - Test suite
- `scripts/` - Python analysis and admin scripts
- `notebooks/` - Jupyter notebooks for analysis
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

## Deployment Reference

**Project Structure:**
- Backend: `~/Desktop/chattercheatah/app`
- Frontend: `~/Desktop/chattercheatah/client`

**Cloud Run Services:**
- Backend: `chattercheatah` → https://chattercheatah-900139201687.us-central1.run.app
- Frontend: `chattercheatah-frontend` → https://chattercheatah-frontend-900139201687.us-central1.run.app

> **IMPORTANT:** Always use the canonical URL format `https://chattercheatah-900139201687.us-central1.run.app` for all integrations including Cloud Tasks, Twilio/Telnyx webhooks, and SendGrid callbacks. Do NOT use auto-generated Cloud Run URLs like `*-iyv6z6wp7a-uc.a.run.app` as they may point to old/stale deployments.

**Database:**
- Supabase PostgreSQL

**Deploy Commands:**
```bash
# Frontend
cd ~/Desktop/chattercheatah/client
npm run build
gcloud run deploy chattercheatah-frontend --source . --region us-central1 --project chatbots-466618 --allow-unauthenticated

# Backend
cd ~/Desktop/chattercheatah
gcloud run deploy chattercheatah --source . --region us-central1 --project chatbots-466618
```

## Communication Channels

### Web Chat
- Embedded chat widget for websites
- Real-time AI-powered responses
- Lead capture and conversation history

### SMS
- Telnyx-based SMS handling
- Compliance handling (STOP, HELP, etc.)
- Business hours support
- Auto-send links when chatbot promises to text

### Voice
- Telnyx-based AI receptionist for inbound calls
- Real-time voice conversations
- Handoff to human agents

### Email
- Gmail-based email responder
- OAuth 2.0 tenant authentication
- Thread-aware AI responses
- See `docs/EMAIL_RESPONDER_SETUP.md` for setup

## Additional Docs

- `DEVELOPMENT.md` — sync workflow between local and GCP
- `DEPLOYMENT.md` — Cloud Run deployment, secrets, and troubleshooting
- `docs/NEW_TENANT_SETUP.md` — Complete tenant onboarding checklist
- `docs/TELNYX_WEBHOOK_SETUP.md` — Telnyx webhook configuration (CRITICAL for SMS/Voice)
- `docs/EMAIL_RESPONDER_SETUP.md` — Gmail email responder configuration
- `docs/tenant_onboarding.md` — tenant onboarding runbook
- `docs/config_matrix.md` — configuration/secrets matrix (global vs per-tenant)
