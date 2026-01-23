# Deployment Guide

## Cloud Run Deployment

### Prerequisites
- GCP project with billing enabled
- gcloud CLI authenticated
- Secrets created in Secret Manager

### Required Secrets
```bash
# Create secrets (one-time setup)
gcloud secrets create jwt-secret --data-file=-
gcloud secrets create gemini-api-key --data-file=-
gcloud secrets create database-url --data-file=-
gcloud secrets create field-encryption-key --data-file=-
gcloud secrets create telnyx-api-key --data-file=-
gcloud secrets create gmail-client-id --data-file=-
gcloud secrets create gmail-client-secret --data-file=-
```

**Generate encryption key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Environment Variables

#### Secrets (from Secret Manager)
| Variable | Description |
|----------|-------------|
| DATABASE_URL | PostgreSQL connection string (Supabase) |
| JWT_SECRET_KEY | JWT signing secret |
| GEMINI_API_KEY | Google AI API key |
| FIELD_ENCRYPTION_KEY | Fernet key for encrypting sensitive DB fields |
| TELNYX_API_KEY | Telnyx API key for voice/SMS |
| GMAIL_CLIENT_ID | Google OAuth client ID |
| GMAIL_CLIENT_SECRET | Google OAuth client secret |

#### Environment Variables (set directly)
| Variable | Description | Default/Example |
|----------|-------------|-----------------|
| ENVIRONMENT | Runtime environment | `production` |
| GCP_PROJECT_ID | GCP project ID | `chatbots-466618` |
| GCP_REGION | GCP region | `us-central1` |
| GEMINI_MODEL | LLM model to use | `gemini-2.5-flash` |
| REDIS_ENABLED | Enable Redis caching | `false` |
| CHAT_MAX_TOKENS | Max tokens for LLM responses | `8000` |
| GCS_WIDGET_ASSETS_BUCKET | GCS bucket for widget assets | `chattercheetah-widget-assets` |
| TWILIO_WEBHOOK_URL_BASE | Base URL for Twilio webhooks | `https://SERVICE-URL` |
| CLOUD_TASKS_WORKER_URL | URL for Cloud Tasks worker | `https://SERVICE-URL/workers` |
| GMAIL_OAUTH_REDIRECT_URI | Gmail OAuth callback URL | `https://SERVICE-URL/api/v1/email/oauth/callback` |
| GMAIL_PUBSUB_TOPIC | Pub/Sub topic for Gmail notifications | `projects/PROJECT/topics/gmail-push-notifications` |

### Common Issues & Fixes

#### 1. DATABASE_URL parsing error
**Error:** `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL`

**Cause:** Special characters in password not URL-encoded

**Fix:** URL-encode special characters in password:
- `!` → `%21`
- `@` → `%40`
- `#` → `%23`
```bash
gcloud run services update chattercheatah \
  --region us-central1 \
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://postgres:Password%21@/dbname?host=/cloudsql/project:region:instance"
```

#### 2. Missing GEMINI_API_KEY after service update
**Error:** `Missing key inputs argument`

**Cause:** Using `--set-env-vars` or `--set-secrets` overwrites all existing vars/secrets

**Fix:** Use `--update-secrets` to add without overwriting:
```bash
gcloud run services update chattercheatah \
  --region us-central1 \
  --update-secrets="GEMINI_API_KEY=gemini-api-key:latest"
```

#### 3. Gemini quota exhausted (429 RESOURCE_EXHAUSTED)
**Error:** `429 RESOURCE_EXHAUSTED... limit: 0`

**Cause:** Free tier quota exceeded

**Fix Options:**
1. Wait 24 hours for quota reset
2. Enable billing at https://aistudio.google.com
3. Use a different model: `--update-env-vars="GEMINI_MODEL=gemini-2.5-flash"`

#### 4. DNS resolution failure
**Error:** `socket.gaierror: [Errno -3] Temporary failure in name resolution`

**Cause:** DATABASE_URL malformed or Supabase host unreachable

**Fix:** Verify DATABASE_URL in Secret Manager is correct:
```bash
gcloud secrets versions access latest --secret=database-url --project=chatbots-466618
```

#### 5. Telnyx webhook issues (404 or 405 errors)
**Errors:**
- 404: Webhook returns "not found" or messages not processed
- 405: Portal shows "Failed" deliveries (but SMS actually sent)

**Cause:** Incorrect webhook URL paths configured in Telnyx Portal.

**Correct Webhook URLs:**
| Webhook | Correct Path |
|---------|--------------|
| Inbound SMS | `/api/v1/telnyx/sms/inbound` |
| Status Callback | `/api/v1/telnyx/sms/status` |

**Common Mistakes:**
- Using `/api/v1/sms/telnyx/status` (swapped segments) → causes 405
- Using `/api/v1/telnyx/inbound` (legacy, still works for inbound)

**Fix:** Update webhooks in Telnyx Portal:
1. Go to Telnyx Portal → Messaging → Messaging Profiles
2. Select your messaging profile
3. **Inbound** tab: Set webhook to `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound`
4. **Outbound** tab: Set Status Callback URL to `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
5. Save changes

#### 6. Datetime timezone mismatch error
**Error:** `TypeError: can't subtract offset-naive and offset-aware datetimes`

**Cause:** Mixing `datetime.now(timezone.utc)` (aware) with database timestamps (naive)

**Fix:** Use `datetime.utcnow()` for naive datetimes when working with SQLAlchemy/PostgreSQL that stores naive UTC timestamps.

#### 7. Chat responses truncated mid-sentence
**Error:** Bot responses cut off (e.g., "We offer a" with no completion)

**Cause:** Hardcoded 500 token limit in LLM calls too restrictive

**Fix:** Token limit is now configurable via `CHAT_MAX_TOKENS` env var (default: 8000)
```bash
gcloud run services update chattercheatah \
  --region us-central1 \
  --update-env-vars="CHAT_MAX_TOKENS=2000"
```

### SMS Integration Notes

**Opt-in Policy:** The SMS service assumes users have already opted in when they text the number. STOP and HELP keywords are handled for compliance, but no opt-in verification is performed.

**Webhook Configuration:** See Issue #5 above for correct Telnyx webhook URLs.

**Debugging SMS Issues:**
```bash
# Check recent SMS webhook logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=chattercheatah AND textPayload=~'SMS'" --limit 50

# Check for errors in Telnyx webhooks
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=chattercheatah AND textPayload=~'telnyx'" --limit 30
```

### Deploying Updates
```bash
# Build and deploy
gcloud builds submit --tag us-central1-docker.pkg.dev/PROJECT/REPO/chattercheatah
gcloud run deploy chattercheatah \
  --image us-central1-docker.pkg.dev/PROJECT/REPO/chattercheatah \
  --region us-central1

# Or use the deploy script
./scripts/deploy-cloud-run.sh
```

### Verifying Deployment
```bash
# Health check
curl https://YOUR-SERVICE-URL/health

# Test chat endpoint
curl -X POST https://YOUR-SERVICE-URL/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "business_id": "test", "tenant_id": 1}'

# Check logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=chattercheatah AND severity>=WARNING" --limit 20
```

### Current Production Config
- **Service URL:** https://chattercheatah-900139201687.us-central1.run.app
- **Region:** us-central1
- **Database:** Supabase (PostgreSQL) - aws-1-us-east-2.pooler.supabase.com
- **Model:** gemini-2.5-flash
