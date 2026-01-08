# Configuration & Secrets Matrix

This matrix lists the configuration values the system expects, where they live, and where they’re used.

Conventions:

- **Global** = applies to the whole deployment (shared across tenants).
- **Per-tenant** = stored in the database and scoped by `tenant_id`.
- **Source of truth**:
  - Env = environment variable (local `.env` or Cloud Run env var)
  - Secret Manager = mounted into env vars on Cloud Run
  - DB = Postgres (Cloud SQL)

---

## Global configuration (Env / Secret Manager)

| Config name | Scope | Purpose | Where used | Source of truth | Example value |
|---|---|---|---|---|---|
| `DATABASE_URL` | Global | Postgres connection string (async) | `app/settings.py` | Secret Manager / Env | `postgresql+asyncpg://app_user:<redacted>@/chattercheatah?host=/cloudsql/project:region:instance` |
| `CLOUD_SQL_INSTANCE_CONNECTION_NAME` | Global | Cloud SQL instance connection name (informational; not required if `DATABASE_URL` is complete) | `app/settings.py` | Env | `project:region:instance` |
| `CLOUD_SQL_DATABASE_NAME` | Global | Cloud SQL database name (informational) | `app/settings.py` | Env | `chattercheatah` |
| `JWT_SECRET_KEY` | Global | JWT signing key | `app/core/auth.py` | Secret Manager | `<redacted>` |
| `JWT_ALGORITHM` | Global | JWT algorithm | `app/core/auth.py` | Env | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Global | Token TTL | `app/core/auth.py` | Env | `720` |
| `ENVIRONMENT` | Global | Runtime environment | `app/settings.py` | Env | `production` |
| `LOG_LEVEL` | Global | Logging level | `app/logging_config.py` | Env | `INFO` |
| `API_V1_PREFIX` | Global | API prefix | `app/main.py` | Env | `/api/v1` |
| `REDIS_ENABLED` | Global | Enable Redis | `app/infrastructure/redis.py` | Env | `false` |
| `REDIS_URL` | Global | Redis connection | `app/infrastructure/redis.py` | Env | `redis://localhost:6379/0` |
| `REDIS_HOST` | Global | Redis host (not used if `REDIS_URL` is set) | `app/settings.py` | Env | `localhost` |
| `REDIS_PORT` | Global | Redis port (not used if `REDIS_URL` is set) | `app/settings.py` | Env | `6379` |
| `IDEMPOTENCY_TTL_SECONDS` | Global | Idempotency cache TTL | `app/api/middleware.py` | Env | `3600` |
| `GCP_PROJECT_ID` | Global | GCP project id | `app/infrastructure/cloud_tasks.py` | Env | `chatbots-466618` |
| `GCP_REGION` | Global | GCP region | `app/settings.py` | Env | `us-central1` |
| `CLOUD_TASKS_QUEUE_NAME` | Global | Cloud Tasks queue name | `app/infrastructure/cloud_tasks.py` | Env | `sms-processing` |
| `CLOUD_TASKS_LOCATION` | Global | Cloud Tasks location | `app/infrastructure/cloud_tasks.py` | Env | `us-central1` |
| `CLOUD_TASKS_WORKER_URL` | Global | Worker URL for SMS jobs | `app/api/routes/sms_webhooks.py` | Env | `https://<service>/workers/sms` |
| `CLOUD_TASKS_EMAIL_WORKER_URL` | Global | Worker URL for email jobs | `app/api/routes/email_webhooks.py` | Env | `https://<service>/workers/email` |
| `TWILIO_ACCOUNT_SID` | Global | Default Twilio SID (fallback) | `app/infrastructure/twilio_client.py` | Secret Manager / Env | `ACxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Global | Default Twilio token (fallback) | `app/infrastructure/twilio_client.py` | Secret Manager / Env | `<redacted>` |
| `TWILIO_WEBHOOK_URL_BASE` | Global | Base URL for Twilio callbacks | `app/api/routes/voice_webhooks.py` | Env | `https://<service>.run.app` |
| `GMAIL_CLIENT_ID` | Global | Gmail OAuth client id | `app/infrastructure/gmail_client.py` | Secret Manager / Env | `<redacted>.apps.googleusercontent.com` |
| `GMAIL_CLIENT_SECRET` | Global | Gmail OAuth client secret | `app/infrastructure/gmail_client.py` | Secret Manager / Env | `<redacted>` |
| `GMAIL_OAUTH_REDIRECT_URI` | Global | OAuth redirect/callback URI | `app/api/routes/tenant_email.py` | Env | `https://<service>/api/v1/email/oauth/callback` |
| `GMAIL_PUBSUB_TOPIC` | Global | Pub/Sub topic for Gmail watch | `app/infrastructure/pubsub.py` | Env | `projects/<project>/topics/gmail-push-notifications` |
| `FRONTEND_URL` | Global | Frontend base URL for redirects | `app/api/routes/tenant_email.py` | Env | `https://<frontend>` |
| `GEMINI_API_KEY` | Global | Gemini API key | `app/llm/gemini_client.py` | Secret Manager / Env | `<redacted>` |
| `GEMINI_MODEL` | Global | Gemini model name | `app/llm/gemini_client.py` | Env | `gemini-3-flash-preview` |
| `AI_INTEGRATIONS_GEMINI_API_KEY` | Global | Alternate Gemini key source | `app/llm/gemini_client.py` | Env | `<redacted>` |
| `AI_INTEGRATIONS_GEMINI_BASE_URL` | Global | Alternate Gemini base URL | `app/llm/gemini_client.py` | Env | `https://...` |
| `CHAT_MAX_TURNS` | Global | Chat guardrail (currently not wired into `ChatService`) | `app/settings.py` | Env | `20` |
| `CHAT_TIMEOUT_SECONDS` | Global | Chat guardrail (currently not wired into `ChatService`) | `app/settings.py` | Env | `300` |
| `CHAT_FOLLOW_UP_NUDGE_TURN` | Global | Chat guardrail (currently not wired into `ChatService`) | `app/settings.py` | Env | `3` |

### Frontend config (Vite)

| Config name | Scope | Purpose | Where used | Source of truth | Example value |
|---|---|---|---|---|---|
| `VITE_API_URL` | Global | Frontend API base URL | `client/src/api/client.js` | Frontend env | `http://localhost:8000/api/v1` |

---

## Per-tenant configuration (DB)

| Config name | Scope | Purpose | Where used | Source of truth | Example value |
|---|---|---|---|---|---|
| `tenants.id` | Per-tenant | Primary tenant identifier | throughout | DB | `1042` |
| `tenants.subdomain` | Per-tenant | Unique tenant slug | tenant lookup | DB | `exampleco` |
| `users.role` | Per-tenant/global | Authorization role | `app/api/deps.py` | DB | `tenant_admin` |
| `tenant_business_profiles.*` | Per-tenant | Shared business facts | profile/voice services | DB | `business_name="Example Customer"` |
| `prompt_bundles.*` + `prompt_sections.*` | Global + per-tenant | Prompt system base + overlays | `app/domain/services/prompt_service.py` | DB | (varies) |
| `tenant_sms_configs.*` | Per-tenant | SMS settings & Twilio mapping | SMS webhook + services | DB | `twilio_phone_number="+15555550123"` |
| `tenant_voice_configs.*` | Per-tenant | Voice greeting/handoff/escalation | voice webhook + services | DB | `handoff_mode="take_message"` |
| `tenant_email_configs.*` | Per-tenant | Gmail OAuth tokens/settings/watch | email services | DB | `gmail_email="ops@exampleco.test"` |
| `email_conversations.*` | Per-tenant | Gmail thread → internal conversation mapping | email services | DB | `gmail_thread_id="18c..."` |

---

## Notes / gaps to track

- Per-tenant secrets stored in DB today include Twilio auth tokens and Gmail refresh tokens; plan to encrypt at rest or move to a dedicated secret store.
- CORS is currently `*` (not environment-configurable yet).
- The public chat endpoint accepts a raw `tenant_id`; consider adding a tenant public token or signed embed key.
