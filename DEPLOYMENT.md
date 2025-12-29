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
