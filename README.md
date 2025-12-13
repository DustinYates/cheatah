# Chatter Cheetah

Multi-tenant AI customer communication platform built on GCP.

## Phase 0

This is the foundational backend architecture phase, focusing on:
- Multi-tenant architecture with strict tenant isolation
- Core persistence (Tenants, Users, Conversations, Messages, Leads, Prompts)
- Prompt system with global base and tenant overrides
- LLM abstraction layer (Gemini Flash 2.5)
- Redis caching and idempotency
- Analytics event hooks

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: Cloud SQL (Postgres)
- **Cache**: Redis (MemoryStore)
- **Package Manager**: uv
- **Deployment**: Cloud Run
- **LLM**: Gemini Flash 2.5 via Google Generative AI

## Setup

### Prerequisites

- Python 3.11+
- uv (https://github.com/astral-sh/uv)
- Docker and Docker Compose (for local services)

### Installation

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

## Development

### Running Tests

```bash
uv run pytest
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

