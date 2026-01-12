# Deployment Guide

## Cloud Run Deployment

### Prerequisites
- GCP project with billing enabled
- gcloud CLI authenticated
- Secrets created in Secret Manager

### Required Secrets
```bash
# Create secrets (one-time setup)
gcloud secrets create gemini-api-key --data-file=-
gcloud secrets create jwt-secret --data-file=-
gcloud secrets create database-url --data-file=-
```

### Environment Variables
| Variable | Description | Example |
|----------|-------------|---------|
| DATABASE_URL | PostgreSQL connection string (Supabase) | `postgresql://postgres.xxxxx:PASSWORD@aws-1-us-east-2.pooler.supabase.com:5432/postgres` |
| GEMINI_API_KEY | Google AI API key | From Secret Manager |
| GEMINI_MODEL | Model to use | `gemini-3-flash-preview` |

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
3. Use a different model: `--update-env-vars="GEMINI_MODEL=gemini-1.5-flash"`

#### 4. DNS resolution failure
**Error:** `socket.gaierror: [Errno -3] Temporary failure in name resolution`

**Cause:** DATABASE_URL malformed or Supabase host unreachable

**Fix:** Verify DATABASE_URL in Secret Manager is correct:
```bash
gcloud secrets versions access latest --secret=database-url --project=chatbots-466618
```

#### 5. Telnyx SMS webhooks not received (404)
**Error:** Telnyx webhook returns 404 or messages not processed

**Cause:** Webhook URL mismatch - Telnyx may be configured with `/api/v1/telnyx/inbound` but code expects `/api/v1/telnyx/sms/inbound`

**Fix:** The endpoint now accepts both paths. When configuring Telnyx webhook URL, either works:
- `https://YOUR-SERVICE-URL/api/v1/telnyx/inbound`
- `https://YOUR-SERVICE-URL/api/v1/telnyx/sms/inbound`

#### 6. Datetime timezone mismatch error
**Error:** `TypeError: can't subtract offset-naive and offset-aware datetimes`

**Cause:** Mixing `datetime.now(timezone.utc)` (aware) with database timestamps (naive)

**Fix:** Use `datetime.utcnow()` for naive datetimes when working with SQLAlchemy/PostgreSQL that stores naive UTC timestamps.

#### 7. Telnyx SMS Status Webhook returns 405 Method Not Allowed
**Error:** Telnyx portal shows "Failed" deliveries with error code 405

**Cause:** Webhook URL path is incorrect - `/api/v1/sms/telnyx/status` instead of `/api/v1/telnyx/sms/status`

**Impact:**
- SMS messages WILL send successfully
- But delivery status callbacks won't be received
- Portal shows all messages as "Failed" even though they were delivered

**Fix:** Update webhook URL in Telnyx Messaging Profile:
1. Go to Telnyx Portal → Messaging → Messaging Profiles
2. Select your messaging profile
3. Go to **Outbound** tab
4. Update **Status Callback URL** to: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
5. ⚠️ Verify the path is `/telnyx/sms/status` NOT `/sms/telnyx/status`
6. Save changes

#### 8. Chat responses truncated mid-sentence
**Error:** Bot responses cut off (e.g., "We offer a" with no completion)

**Cause:** Hardcoded 500 token limit in LLM calls too restrictive

**Fix:** Token limit is now configurable via `CHAT_MAX_TOKENS` env var (default: 1500)
```bash
gcloud run services update chattercheatah \
  --region us-central1 \
  --update-env-vars="CHAT_MAX_TOKENS=2000"
```

### SMS Integration Notes

**Opt-in Policy:** The SMS service assumes users have already opted in when they text the number. STOP and HELP keywords are handled for compliance, but no opt-in verification is performed.

**Telnyx Webhook Configuration:**
- Inbound SMS Webhook URL: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound`
  - Alternate path (deprecated): `/api/v1/telnyx/inbound`
- SMS Status Callback Webhook URL: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
  - **CRITICAL**: Use the correct path - `/api/v1/telnyx/sms/status` NOT `/api/v1/sms/telnyx/status`
  - Common mistake: Swapping "telnyx" and "sms" in the path will cause 405 Method Not Allowed errors

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
- **Model:** gemini-3-flash-preview
