# Chatter Cheetah

## Overview
Multi-tenant AI customer communication platform built with FastAPI and PostgreSQL. This is a backend API service that provides:
- Multi-tenant architecture with strict tenant isolation
- AI-powered chat via Google Gemini
- SMS integration via Twilio
- Authentication with JWT tokens

## Project Structure
- `app/` - Main application code
  - `api/` - FastAPI routes and middleware
  - `domain/` - Domain services (chat, SMS, compliance)
  - `persistence/` - Database models and repositories
  - `llm/` - LLM abstraction layer (Gemini)
  - `infrastructure/` - Redis, Cloud Tasks, Twilio client
  - `core/` - Auth, tenant context, idempotency
  - `workers/` - Background task workers
- `alembic/` - Database migrations
- `tests/` - Test suite
- `static/` - Static files (admin dashboard, chat widget)

## Technology Stack
- **Language**: Python 3.11
- **Framework**: FastAPI
- **Database**: PostgreSQL (Replit built-in)
- **Cache**: Redis (optional, disabled by default)
- **LLM**: Google Gemini

## Running the Application
The API server runs on port 5000 with:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

## API Documentation
- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`
- Admin Dashboard: `/static/admin-dashboard.html`

## Environment Variables
Required for full functionality:
- `DATABASE_URL` - PostgreSQL connection string (auto-configured)
- `JWT_SECRET_KEY` - Secret for JWT token signing (defaults to dev value)
- `GEMINI_API_KEY` - Google Gemini API key (for AI features)
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` - Twilio credentials (for SMS)

## Database Migrations
Run migrations with:
```bash
python -c "from alembic.config import main; import sys; sys.argv = ['alembic', 'upgrade', 'head']; main()"
```

## Recent Changes
- 2024-12-13: Configured for Replit environment
  - Fixed Python version to 3.11
  - Made Redis optional for development
  - Configured DATABASE_URL conversion for asyncpg
  - Set up deployment configuration
