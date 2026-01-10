# ChatterCheetah Infrastructure & Secrets Documentation

## 1. Global Environment Variables

| Variable Name | Description | Scope | Example Value | Rotation |
|--------------|-------------|-------|---------------|----------|
| `ENVIRONMENT` | Runtime environment | global | `production` | N/A |
| `GCP_PROJECT_ID` | Google Cloud project ID | global | `chatbots-466618` | N/A |
| `GCP_REGION` | Google Cloud region | global | `us-central1` | N/A |
| `LOG_LEVEL` | Application log level | global | `INFO` | N/A |
| `API_V1_PREFIX` | API route prefix | global | `/api/v1` | N/A |
| `API_BASE_URL` | Public base URL for embed code | global | `https://chattercheatah-900139201687.us-central1.run.app` | N/A |

### API Keys (Secrets)

| Secret Name | Description | Scope | Where Used |
|-------------|-------------|-------|------------|
| `JWT_SECRET_KEY` | JWT token signing key | global | Authentication |
| `GEMINI_API_KEY` | Google Gemini LLM API key | global | Chat/Voice AI responses |
| `DATABASE_URL` | Supabase Postgres connection string | global | All data persistence |
| `TELNYX_API_KEY` | Telnyx API v2 key (global) | global | Voice transcript fetching |
| `GMAIL_CLIENT_ID` | Google OAuth client ID | global | Email integration OAuth |
| `GMAIL_CLIENT_SECRET` | Google OAuth client secret | global | Email integration OAuth |
| `GOOGLE_MAPS_API_KEY` | Google Maps API key | global | Location services (unused) |

---

## 2. LLM / AI Providers

### Gemini (Primary LLM)

| Setting | Value |
|---------|-------|
| **Provider** | Google Gemini |
| **API Key Secret** | `gemini-api-key` |
| **Model** | `gemini-3-flash-preview` |
| **Max Tokens** | 8000 (chat), 1000 (voice extraction) |
| **Temperature** | 0.3 (chat), 0.1 (extraction) |
| **Region** | N/A (Google API) |

### Usage Contexts

- **Chat Service**: Multi-turn conversations via web widget
- **Voice Transcript Extraction**: Extracts name, email, intent from call transcripts
- **Prompt Interview**: AI-guided business onboarding

---

## 3. Database Layer (Supabase / Postgres)

### Primary Database

| Setting | Value |
|---------|-------|
| **Provider** | Supabase (PostgreSQL) |
| **Host** | `aws-0-us-central1.pooler.supabase.com` |
| **Port** | 5432 (pooler: 6543) |
| **Database Name** | `postgres` |
| **SSL Mode** | `require` (converted to `ssl=require` for asyncpg) |
| **Connection Secret** | `database-url` |
| **Driver** | `postgresql+asyncpg://` |

### Cloud SQL Connection (GCP)

| Setting | Value |
|---------|-------|
| **Instance** | `chatbots-466618:us-central1:chattercheetah-db` |
| **Auto-connect** | Yes (via Cloud Run annotation) |

### Database Tables

| Table | Description |
|-------|-------------|
| `tenants` | Business/organization accounts |
| `users` | System users with roles |
| `tenant_business_profiles` | Scraped business info |
| `tenant_sms_configs` | Per-tenant SMS settings |
| `tenant_voice_configs` | Per-tenant voice settings |
| `tenant_email_configs` | Per-tenant email settings |
| `tenant_widget_configs` | Chat widget customization |
| `tenant_customer_service_configs` | Zapier/CRM integration |
| `tenant_prompt_configs` | Dynamic prompt assembly |
| `prompt_bundles` | AI prompt templates |
| `conversations` | Chat/SMS conversations |
| `contacts` | Customer contact records |
| `leads` | Lead records from all channels |
| `calls` | Voice call records |
| `call_summaries` | AI-generated call summaries |
| `sms_opt_ins` | SMS consent tracking |
| `escalations` | Human escalation requests |
| `notifications` | In-app notifications |
| `zapier_requests` | Zapier webhook tracking |
| `jackrabbit_customers` | CRM cache |

### Migration Tooling

- **Tool**: Alembic
- **Location**: `/alembic/versions/`

### Redis (Optional)

| Setting | Value |
|---------|-------|
| **Enabled** | `false` (disabled in production) |
| **Host** | `localhost` |
| **Port** | 6379 |
| **Purpose** | Caching (not currently used) |

---

## 4. Telephony & Messaging (Telnyx / Twilio / Voxie)

### Telnyx (Primary - Voice + SMS)

| Setting | Location | Description |
|---------|----------|-------------|
| **Global API Key** | Secret: `telnyx-api-key` | For AI conversation API |
| **Per-tenant API Key** | `tenant_sms_configs.telnyx_api_key` | Tenant-specific |
| **Messaging Profile ID** | `tenant_sms_configs.telnyx_messaging_profile_id` | Required for SMS |
| **Connection ID** | `tenant_sms_configs.telnyx_connection_id` | Required for Voice/TeXML |
| **Phone Number** | `tenant_sms_configs.telnyx_phone_number` | Tenant's phone number |

### Telnyx AI Assistant Configuration

| Setting | Value |
|---------|-------|
| **Assistant ID** | `d3d25f89-a4df-4ca0-8657-7fe2f53ce348` |
| **Insight Group** | `0f29632f-e2e6-424a-973f-4d738ea758d8` |

### Webhooks (MANDATORY)

| Webhook | URL | Events |
|---------|-----|--------|
| **SMS Inbound** | `/webhooks/telnyx/sms` | Incoming SMS |
| **SMS Status** | `/webhooks/telnyx/sms-status` | Delivery status |
| **Voice AI Complete** | `/webhooks/telnyx/ai-call-complete` | Call ended |
| **Voice Progress** | `/webhooks/telnyx/call-progress` | Call state changes |
| **Dynamic Variables** | `/webhooks/telnyx/dynamic-variables` | Prompt injection |
| **AI Insights** | `/webhooks/telnyx/ai-insights` | (not firing - bug) |

### Twilio (Legacy/Alternative)

| Setting | Location | Description |
|---------|----------|-------------|
| **Account SID** | `tenant_sms_configs.twilio_account_sid` | Per-tenant |
| **Auth Token** | `tenant_sms_configs.twilio_auth_token` | Per-tenant |
| **Phone Number** | `tenant_sms_configs.twilio_phone_number` | Per-tenant |
| **Webhook Base URL** | `TWILIO_WEBHOOK_URL_BASE` env var | Global |

### Voxie (SMS Only)

| Setting | Location | Description |
|---------|----------|-------------|
| **API Key** | `tenant_sms_configs.voxie_api_key` | Per-tenant |
| **Team ID** | `tenant_sms_configs.voxie_team_id` | Per-tenant |
| **Phone Number** | `tenant_sms_configs.voxie_phone_number` | Per-tenant |

### Tenant → Phone Number Routing

```
tenant_sms_configs.telnyx_phone_number → Tenant ID lookup
tenant_sms_configs.twilio_phone_number → Tenant ID lookup
tenant_sms_configs.voxie_phone_number → Tenant ID lookup
```

---

## 5. Authentication & Identity

### Admin Authentication

| Setting | Value |
|---------|-------|
| **Method** | JWT Bearer tokens |
| **Algorithm** | HS256 |
| **Secret** | `jwt-secret` (GCP Secret) |
| **Expiration** | 720 minutes (12 hours) |

### User Roles

| Role | Description |
|------|-------------|
| `admin` | System-wide admin (ChatterCheetah staff) |
| `tenant_admin` | Tenant administrator |
| `user` | Regular tenant user |

### API Authentication

- All `/api/v1/*` routes require Bearer token
- Public routes: `/chat/*`, `/webhooks/*`, `/health`

### OAuth (Gmail)

| Setting | Value |
|---------|-------|
| **Provider** | Google OAuth 2.0 |
| **Client ID** | Secret: `gmail-client-id` |
| **Client Secret** | Secret: `gmail-client-secret` |
| **Redirect URI** | `{API_BASE_URL}/api/v1/email/oauth/callback` |
| **Scopes** | `gmail.readonly`, `gmail.send`, `gmail.modify` |

---

## 6. Cloud Infrastructure (Cloud Run / GCP)

### Cloud Run Service

| Setting | Value |
|---------|-------|
| **Service Name** | `chattercheatah` |
| **Project ID** | `chatbots-466618` |
| **Region** | `us-central1` |
| **Service Account** | `900139201687-compute@developer.gserviceaccount.com` |
| **Image Registry** | `us-central1-docker.pkg.dev/chatbots-466618/cloud-run-source-deploy/chattercheatah` |

### Resource Limits

| Setting | Value |
|---------|-------|
| **CPU** | 1 vCPU |
| **Memory** | 1 GiB |
| **Min Instances** | 1 (always warm) |
| **Max Instances** | 10 |
| **Concurrency** | 80 requests/instance |
| **Timeout** | 300 seconds |
| **Startup CPU Boost** | Enabled |

### URLs

| Type | URL |
|------|-----|
| **Primary** | `https://chattercheatah-900139201687.us-central1.run.app` |
| **Alternate** | `https://chattercheatah-iyv6z6wp7a-uc.a.run.app` |

### Secrets Manager Integration

| Secret Name | Mounted As |
|-------------|------------|
| `jwt-secret` | `JWT_SECRET_KEY` |
| `gemini-api-key` | `GEMINI_API_KEY` |
| `gmail-client-id` | `GMAIL_CLIENT_ID` |
| `gmail-client-secret` | `GMAIL_CLIENT_SECRET` |
| `database-url` | `DATABASE_URL` |
| `telnyx-api-key` | `TELNYX_API_KEY` |

### IAM Roles Required

- `roles/run.invoker` - Cloud Run invocation
- `roles/secretmanager.secretAccessor` - Secrets access
- `roles/cloudsql.client` - Cloud SQL connection
- `roles/pubsub.subscriber` - Gmail push notifications

### Domain Mapping

- **REQUIRED - VALUE TBD**: Custom domain configuration

---

## 7. Webhooks & External Integrations

### Inbound Webhooks

| Endpoint | Source | Purpose |
|----------|--------|---------|
| `/webhooks/telnyx/sms` | Telnyx | SMS messages |
| `/webhooks/telnyx/sms-status` | Telnyx | SMS delivery status |
| `/webhooks/telnyx/ai-call-complete` | Telnyx | Voice call ended |
| `/webhooks/telnyx/call-progress` | Telnyx | Call state updates |
| `/webhooks/telnyx/dynamic-variables` | Telnyx | Prompt injection |
| `/webhooks/telnyx/ai-insights` | Telnyx | Caller insights (broken) |
| `/webhooks/twilio/sms` | Twilio | SMS messages |
| `/webhooks/twilio/status` | Twilio | SMS status |
| `/webhooks/voxie/sms` | Voxie | SMS messages |
| `/webhooks/email/gmail-push` | Google Pub/Sub | Gmail notifications |
| `/webhooks/zapier/customer-lookup-callback` | Zapier | CRM responses |
| `/webhooks/customer-service/voice` | Telnyx | CS voice calls |
| `/webhooks/customer-service/sms` | Telnyx | CS SMS |

### Signature Verification

| Provider | Header | Method |
|----------|--------|--------|
| Telnyx | `telnyx-signature-ed25519` | ED25519 |
| Twilio | `X-Twilio-Signature` | HMAC-SHA1 |
| Zapier | `X-Zapier-Signature` | HMAC |

### Event Types Handled

- SMS: `message.received`, `message.sent`, `message.finalized`
- Voice: `call.initiated`, `call.answered`, `call.hangup`, `assistant.initialization`
- Email: Gmail push notification

---

## 8. Email & Notifications

### Gmail Integration

| Setting | Value |
|---------|-------|
| **OAuth Provider** | Google |
| **Pub/Sub Topic** | `projects/chatbots-466618/topics/gmail-push-notifications` |
| **Watch Expiration** | 7 days (auto-renewed) |

### Per-Tenant Email Config

| Field | Description |
|-------|-------------|
| `is_enabled` | Email responder enabled |
| `gmail_refresh_token` | OAuth refresh token |
| `gmail_access_token` | Current access token |
| `gmail_watch_expiration` | Watch renewal time |
| `auto_reply_enabled` | Auto-respond to emails |
| `response_delay_minutes` | Delay before responding |

### SMTP / Sender (REQUIRED - NOT CURRENTLY DEFINED)

- **REQUIRED - VALUE TBD**: Outbound email sender configuration
- **REQUIRED - VALUE TBD**: DKIM/SPF requirements

---

## 9. Multi-Tenant Architecture Breakdown

### System-Wide (Shared)

- GCP Project and Cloud Run service
- Gemini API key
- Global Telnyx API key (for conversation fetching)
- Database schema (all tenants in same DB)
- JWT secret

### Admin-Only

- User management across tenants
- Tenant creation/deletion
- System-wide prompt templates
- Phone number provisioning

### Tenant-Specific

| Resource | Storage |
|----------|---------|
| API Keys (Telnyx/Twilio) | `tenant_sms_configs` table |
| Phone Numbers | `tenant_sms_configs` table |
| Webhooks | Derived from phone number lookup |
| Business Profile | `tenant_business_profiles` table |
| Prompt Bundles | `prompt_bundles` table |
| Widget Customization | `tenant_widget_configs` table |
| Voice Config | `tenant_voice_configs` table |
| Email Config | `tenant_email_configs` table |
| CRM Integration | `tenant_customer_service_configs` table |

### Tenant Isolation

- All queries filtered by `tenant_id`
- Phone number → tenant lookup for webhooks
- JWT contains `tenant_id` claim for authorization

### Rate Limits (REQUIRED - NOT CURRENTLY DEFINED)

- **REQUIRED - VALUE TBD**: Per-tenant API rate limits
- **REQUIRED - VALUE TBD**: SMS/Voice quotas

---

## 10. Secrets Storage & Rotation

### GCP Secret Manager Secrets

| Secret Name | Created | Purpose |
|-------------|---------|---------|
| `jwt-secret` | 2025-12-14 | JWT signing |
| `gemini-api-key` | 2025-12-14 | LLM API |
| `database-url` | 2025-12-14 | Database connection |
| `gmail-client-id` | 2025-12-24 | OAuth |
| `gmail-client-secret` | 2025-12-24 | OAuth |
| `google-maps-api-key` | 2025-12-01 | Maps (unused) |
| `telnyx-api-key` | 2026-01-10 | Voice API |

### Local Development

- Secrets in `.env` file (git-ignored)
- `.env.sync` for sync reference

### Rotation Strategy (REQUIRED - NOT CURRENTLY DEFINED)

- **REQUIRED - VALUE TBD**: Secret rotation schedule
- **REQUIRED - VALUE TBD**: Rotation procedures

### Least-Privilege Access

- Cloud Run service account has `secretAccessor` role
- Only specific secrets mounted to service

### Audit Logging (REQUIRED - NOT CURRENTLY DEFINED)

- **REQUIRED - VALUE TBD**: Secret access audit logging

---

## 11. Missing / Assumed Items

### REQUIRED BUT NOT CURRENTLY DEFINED

| Item | Category | Notes |
|------|----------|-------|
| Custom domain | Cloud Run | Currently using run.app URLs |
| SMTP sender config | Email | No outbound email sender configured |
| DKIM/SPF setup | Email | Required for email deliverability |
| Rate limiting | Application | No per-tenant rate limits |
| Secret rotation | Security | No rotation schedule defined |
| Audit logging | Security | No comprehensive audit trail |
| Backup strategy | Database | Supabase handles backups |
| Monitoring/alerting | Ops | No alerting configured |
| Error tracking | Ops | Using Cloud Logging only |
| CI/CD pipeline | DevOps | Manual deployments via gcloud |
| Staging environment | DevOps | Production only |
| Redis deployment | Caching | Disabled, not deployed |
| Telnyx Insights fix | Telephony | insight_group_id not propagating |
| ScrapingBee API key | Scraping | In code but not in secrets |

---

## Deployment Commands

### Deploy to Cloud Run

```bash
cd /Users/dustinyates/Desktop/chattercheetah
gcloud run deploy chattercheatah --source . --region us-central1
```

### Update Secrets

```bash
# Add new secret
echo -n "secret_value" | gcloud secrets create SECRET_NAME --data-file=- --replication-policy=automatic

# Mount to Cloud Run
gcloud run services update chattercheatah --region us-central1 \
  --set-secrets="SECRET_NAME=secret-name:latest"
```

### Build Frontend

```bash
cd client && npm run build
```

---

*Document generated: 2026-01-10*
*Service revision: chattercheatah-00331-hvr*
