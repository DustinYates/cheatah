# Chatter Cheetah

## Overview
Multi-tenant AI customer communication platform built with FastAPI and PostgreSQL with a React frontend. Each client signs in and gets their own dashboard to manage:
- Leads and conversion tracking
- AI prompts for customer communication
- Verified contacts

## Project Structure
- `app/` - Backend FastAPI application
  - `api/` - Routes and middleware
  - `domain/` - Domain services (chat, SMS, compliance)
  - `persistence/` - Database models and repositories
  - `llm/` - LLM abstraction layer (Gemini)
  - `infrastructure/` - Redis, Cloud Tasks, Twilio client
  - `core/` - Auth, tenant context, idempotency
  - `workers/` - Background task workers
- `client/` - React frontend (Vite)
  - `src/pages/` - Dashboard, Prompts, Contacts, Login
  - `src/components/` - Layout, ProtectedRoute
  - `src/context/` - AuthContext
  - `src/api/` - API client
- `alembic/` - Database migrations
- `tests/` - Test suite

## Technology Stack
- **Backend**: Python 3.11, FastAPI
- **Frontend**: React 18, Vite, Recharts
- **Database**: PostgreSQL (Replit built-in)
- **Cache**: Redis (optional, disabled by default)
- **LLM**: Google Gemini

## Running the Application
Two workflows run simultaneously:
- **Frontend**: React on port 5000 (user-facing)
- **API Server**: FastAPI on port 8000 (backend)

The frontend proxies API requests to the backend.

## API Documentation
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

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
- 2024-12-13: Added multi-tenant chatbot MVP with prompt versioning
  - Gemini AI integration via Replit AI Integrations (no API key needed, billed to credits)
  - PromptBundle/PromptSection models with draft/testing/production workflow
  - Tenants can create prompts, test with real AI, then publish to production
  - Prompt sections support: system, base, pricing, FAQ, business_info, custom scopes
  - Updated Prompts page with bundle management, testing, and publish functionality
  - Embeddable widget (static/chat-widget.js) uses production prompts
- 2024-12-13: Added React frontend
  - Login page with JWT authentication
  - Dashboard with leads chart and recent leads list
  - Prompts page for creating and testing prompts
  - Contacts page for verified contacts
  - Clean, minimal design with sidebar navigation
