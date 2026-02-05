# Tenant Onboarding Runbook (Multi-Tenant + GCP)

This document describes a clean, repeatable tenant onboarding process for this codebase, including concrete examples (using fake/redacted values).

## Terminology

- **Tenant**: A customer/business/organization represented by a row in the `tenants` table.
- **Tenant ID**: Integer primary key `tenants.id` (example: `1042`).
- **Global admin**: A `users` row with `tenant_id = NULL` and `role = "admin"`. Global admins can impersonate a tenant with the `X-Tenant-Id` header.

---

## 1) Tenant ID & Provisioning Flow

### How a tenant is uniquely identified

This system uses:

- **Primary identifier**: `tenants.id` (integer).
- **Secondary identifier**: `tenants.subdomain` (unique string).

Example:

```text
tenant_id = 1042
subdomain = "exampleco"
```

### Where tenant_id is stored/enforced

**Database**

- Most tenant-owned tables include a `tenant_id` foreign key column referencing `tenants.id`.
- Some tables (notably `messages`) do not have `tenant_id`; tenant isolation is enforced by joining through `conversations`.

**API/auth**

- Authenticated endpoints resolve tenant context from the authenticated `User` row.
- A global admin may override tenant context via `X-Tenant-Id` header.

**Query layer**

- Repositories generally apply `WHERE <model>.tenant_id = :tenant_id` to enforce row-level tenant isolation.

### Step-by-step provisioning flow (create tenant → admin user → seed defaults → enable integrations → verify)

#### Step 0 — Prereqs (once per environment)

1. Ensure `DATABASE_URL` points to the correct Postgres database (Cloud SQL in prod).
2. Run DB migrations:

```bash
uv run alembic upgrade head
```

#### Step 1 — Create the global admin (once per environment)

This creates the initial operator account used to create tenants and impersonate them.

```bash
uv run python scripts/seed_admin.py
```

Log in via API:

```bash
curl -sS -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@chattercheatah.com","password":"admin123"}'
```

#### Step 2 — Create a tenant

Use the global admin token to create a tenant:

```bash
curl -sS -X POST "$API_BASE/admin/tenants" \
  -H "Authorization: Bearer $GLOBAL_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Example Customer","subdomain":"exampleco","is_active":true}'
```

Example response:

```json
{"id":1042,"name":"Example Customer","subdomain":"exampleco","is_active":true,"created_at":"<timestamp>"}
```

#### Step 3 — Create a tenant admin user

There is no separate “tenant admin creation” endpoint; users are created in a tenant context.

As **global admin**, impersonate the tenant via header:

```bash
curl -sS -X POST "$API_BASE/users" \
  -H "Authorization: Bearer $GLOBAL_ADMIN_JWT" \
  -H "X-Tenant-Id: 1042" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@exampleco.test","password":"<redacted>","role":"tenant_admin"}'
```

#### Step 4 — Seed defaults (prompts + profile)

**Global base prompt (recommended)**

This creates the global prompt bundle inherited by all tenants:

```bash
uv run python scripts/create_base_prompt.py
```

**Tenant prompt**

Create tenant prompt bundle via API (tenant admin required):

```bash
curl -sS -X POST "$API_BASE/tenant-setup/setup-prompt" \
  -H "Authorization: Bearer $TENANT_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"ExampleCo Prompt Bundle",
    "business_prompt":"ExampleCo sells widgets. Hours are Mon-Fri 9-5 CT. Never quote pricing unless present in PRICING section.",
    "faq":"Q: Do you ship? A: Yes, within the US.",
    "rules":"Never request credit card info over chat."
  }'
```

**Business profile**

Populate tenant business profile used across channels:

```bash
curl -sS -X PUT "$API_BASE/tenant/profile" \
  -H "Authorization: Bearer $TENANT_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name":"Example Customer",
    "website_url":"https://exampleco.test",
    "phone_number":"+15555550123",
    "email":"support@exampleco.test"
  }'
```

#### Step 5 — Enable integrations (SMS / Voice / Email)

See section **5) Integrations** below.

#### Step 6 — Verify (smoke tests + isolation)

See **Verification checklist** below.

---

## 2) How tenant isolation works (queries, APIs, storage)

### API-level tenant context

- **Tenant users**: tenant is derived from the authenticated user’s `users.tenant_id`.
- **Global admins**: may impersonate a tenant by providing `X-Tenant-Id: <tenant_id>`.

### Query-level isolation (row-level filtering)

Typical pattern:

```sql
SELECT * FROM leads WHERE tenant_id = 1042;
```

In code, most repositories accept `tenant_id` and apply `WHERE model.tenant_id == tenant_id`.

### Messages are scoped via conversation join

The `messages` table does not include `tenant_id`. To ensure isolation, message lookups join through `conversations` and require `conversations.tenant_id == :tenant_id`.

### Storage paths (recommended convention)

This repo currently stores recording URLs directly (no GCS storage integration yet). If/when adding object storage, use tenant prefixing:

```text
gs://<bucket>/tenants/1042/
```

---

## 3) Database (Supabase / Postgres) onboarding notes

### Connection examples

Supabase via connection pooler (Cloud Run):

```bash
DATABASE_URL=postgresql+asyncpg://user:<redacted>@aws-0-us-central1.pooler.supabase.com:5432/postgres
```

Local Postgres (docker-compose):

```bash
DATABASE_URL=postgresql+asyncpg://chattercheatah:dev_password@localhost:5432/chattercheatah
```

### Migrations and seeding

- Migrate: `uv run alembic upgrade head`
- Seed global admin: `uv run python scripts/seed_admin.py`
- Seed global base prompt: `uv run python scripts/create_base_prompt.py`

---

## 4) LLM configuration & prompts

### Provider & model

- Provider: Gemini (via `google.genai`)
- Model: configured by `GEMINI_MODEL` (example: `gemini-2.5-flash`)
- Auth: `AI_INTEGRATIONS_GEMINI_API_KEY` (if present) else `GEMINI_API_KEY`

### Prompt composition model (global base + tenant overlays)

- Global prompt bundle: `prompt_bundles.tenant_id = NULL` and `status = PRODUCTION`.
- Tenant prompt bundle: `prompt_bundles.tenant_id = <tenant_id>`.
- Composition: global sections + tenant sections are merged by `section_key` (tenant wins on key collision), then ordered.

---

## 5) Integrations runbook (SMS / Voice / Email)

### SMS (Telnyx - Primary)

**Tenant routing**

Inbound webhooks map tenant by:

1) `TenantSmsConfig.telnyx_phone_number == To`, else
2) `TenantSmsConfig.twilio_phone_number == To` (legacy)

**Provisioning steps**

1. Create/update tenant SMS config (admin or internal tooling):
   - Assign `telnyx_phone_number`
   - Set `telnyx_api_key` and `telnyx_messaging_profile_id`
   - Configure 10DLC compliance in Telnyx Portal (required for US SMS)
2. Set up webhooks in Telnyx Portal (see `docs/NEW_TENANT_SETUP.md`)
3. Tenant enables SMS in their settings (`/api/v1/sms/settings`).

**How to test**

- Send an inbound SMS to the tenant's configured number.
- Confirm a conversation is created with `conversations.tenant_id = 1042`.

### Voice (Telnyx AI Assistant - Primary)

**Tenant routing**

Voice calls are handled by Telnyx AI Assistant configured per-tenant:

1) Each tenant has their own AI Assistant in Telnyx Portal
2) Phone number is assigned to the AI Assistant
3) Call completion webhook posts to `/api/v1/telnyx/ai-call-complete`

**Provisioning steps**

1. Create TenantVoiceConfig record (`scripts/setup_voice_configs.py`)
2. Create Telnyx AI Assistant in portal with tenant-specific prompt
3. Assign phone number to AI Assistant
4. Configure webhooks for call events

**How to test**

- Place a call to the tenant number.
- Verify AI responds with tenant-specific information.
- Confirm call records are created in the database.

### Email (Gmail OAuth + Pub/Sub + Cloud Tasks)

**Global setup (once per env)**

Follow `docs/EMAIL_RESPONDER_SETUP.md`:

- Create OAuth client (client ID/secret)
- Configure redirect URI
- Create Pub/Sub topic/subscription
- Grant Gmail push service account Pub/Sub publisher role

**Tenant setup**

1. Tenant starts OAuth: `POST /api/v1/email/oauth/start`
2. Google redirects to `/api/v1/email/oauth/callback`
3. Tokens + connected Gmail address are stored in `tenant_email_configs`
4. Pub/Sub push hits `/api/v1/email/pubsub` and triggers processing

**How to test**

- Use `POST /api/v1/email/pubsub/test` in non-production environments.

---

## 6) Provisioning checklist (copy/paste)

### Manual steps

- [ ] Create tenant (`POST /admin/tenants`)
- [ ] Create tenant admin user (`POST /users` with tenant context)
- [ ] Seed tenant prompt (`POST /tenant-setup/setup-prompt`)
- [ ] Update business profile (`PUT /tenant/profile`)
- [ ] Configure SMS number/credentials (operator/admin workflow)
- [ ] Configure voice number (operator/admin workflow)
- [ ] Connect Gmail (tenant workflow) and enable email responder

### Automated / scriptable steps

- [ ] `uv run alembic upgrade head`
- [ ] `uv run python scripts/seed_admin.py`
- [ ] `uv run python scripts/create_base_prompt.py`

---

## 7) Verification checklist (smoke tests to confirm isolation)

Create two tenants (e.g., `1042` and `2048`) and run:

1. **Auth & tenant context**
   - [ ] Login as tenant admin for each tenant
   - [ ] Login as global admin, set `X-Tenant-Id` to each tenant, verify data views differ

2. **Prompt isolation**
   - [ ] Create a tenant prompt section unique to tenant 1042
   - [ ] Confirm tenant 2048 composed prompt does not include it

3. **CRUD isolation**
   - [ ] Create a lead in tenant 1042
   - [ ] Attempt to fetch that lead while authenticated as tenant 2048 → expect 404/not found

4. **Channel routing**
   - [ ] SMS inbound routes to correct tenant based on `To` and/or `AccountSid`
   - [ ] Voice inbound routes to correct tenant based on `To`
   - [ ] Email Pub/Sub routes to correct tenant based on connected `gmail_email`

---

## 8) BSS (British Swim School) Tenant Onboarding

BSS franchises have specific requirements due to their Jackrabbit integration and voice agent capabilities.

### BSS-Specific Configuration

| Item | Description |
|------|-------------|
| **Jackrabbit Org ID** | `545911` (shared across all BSS locations) |
| **Registration URL Builder** | Uses `app/utils/registration_url_builder.py` for prefilled links |
| **Voice Agent Tools** | `send_registration_link`, `get_classes`, `book_meeting`, `get_available_slots` |

### Telnyx AI Assistant Setup for BSS

1. **Create AI Assistant** in Telnyx Portal with BSS-specific prompt
2. **Assign phone number** to the assistant
3. **Configure webhook tools** with the following URLs (replace `{TENANT_ID}` with actual tenant ID):

| Tool | URL Template |
|------|--------------|
| `send_registration_link` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/send-link?tenant_id={TENANT_ID}` |
| `get_classes` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/get-classes?tenant_id={TENANT_ID}` |
| `book_meeting` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/book-meeting?tenant_id={TENANT_ID}` |
| `get_available_slots` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/get-available-slots?tenant_id={TENANT_ID}` |

> **Note:** For tenant 3 (BSS Cypress-Spring), the `?tenant_id=3` parameter is optional due to the code fallback. For ALL other tenants, it is **REQUIRED**.

### CRITICAL: Tenant ID Resolution for New BSS Franchises

The tool endpoints determine tenant via:
1. `?tenant_id=X` query parameter in the webhook URL
2. `call_control_id` header (voice calls only)
3. **Fallback to tenant 3** (BSS Cypress-Spring) if neither is available

> **⚠️ WARNING: The tenant 3 fallback is ONLY for the first BSS franchise (Cypress-Spring).**
>
> **ALL future BSS franchises MUST have their tenant_id explicitly passed in the tool URLs.**
>
> The fallback exists as a safety net for tenant 3 only. It will NOT work correctly for tenant 4, 5, etc.

**For EVERY new BSS tenant**, you MUST:
1. Create the tenant in the system (get assigned tenant_id, e.g., `4`)
2. Add `?tenant_id=<new_tenant_id>` to **EACH** tool URL in Telnyx Mission Control

Example for a new tenant with ID `4`:
```
https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/send-link?tenant_id=4
https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/get-classes?tenant_id=4
https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/book-meeting?tenant_id=4
https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/get-available-slots?tenant_id=4
```

**DO NOT rely on the fallback for any tenant other than tenant 3.**

### BSS Phone Number Mapping

| Tenant ID | Location | Phone Number | Assistant ID |
|-----------|----------|--------------|--------------|
| 3 | BSS Cypress-Spring | +12817679141 | `assistant-109f3350-874f-4770-87d4-737450280441` |

*Add new BSS franchises to this table as they are onboarded.*

### BSS Voice Agent Prompt

The combined BSS voice agent prompt is maintained at:
- `docs/BSS_VOICE_AGENT_PROMPT_COMBINED.md`

This prompt includes:
- Bilingual (English/Spanish) support
- Location/class information
- Registration link sending via tools
- Jackrabbit class integration

---

## 9) Security notes (support-friendly)

Safe to share:

- Redacted connection strings and env var *names*
- Tenant IDs replaced with fake values
- Screenshots with tokens/secrets removed

Never share:

- OAuth refresh tokens, Telnyx/Twilio auth tokens, JWT secret keys, API keys
- `Authorization: Bearer ...` headers

