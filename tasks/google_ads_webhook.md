# Google Ads Lead Form → ConvoPro Webhook

**Origin:** Ashley (BSS Cypress-Spring) wants to wire her Google Ads lead-form extension directly to ConvoPro, replacing the current email-based ingestion.

## Goal

Accept Google Ads lead-form payloads at a per-tenant URL, store them as `Lead` rows, route into the existing drip + hot-lead notification flows. No Zapier in the path.

## Google Ads payload (reference)

Google Ads POSTs JSON to the tenant's webhook URL when a lead submits:

```json
{
  "lead_id": "TeSt_LeAd_iD",
  "user_column_data": [
    {"column_name": "FULL_NAME",  "string_value": "Jane Doe",        "column_id": "FULL_NAME"},
    {"column_name": "EMAIL",      "string_value": "jane@example.com","column_id": "EMAIL"},
    {"column_name": "PHONE_NUMBER","string_value": "+18005551212",   "column_id": "PHONE_NUMBER"},
    {"column_name": "POSTAL_CODE","string_value": "77433",            "column_id": "POSTAL_CODE"},
    {"column_name": "What age?",  "string_value": "Child",            "column_id": "QUESTION_1"}
  ],
  "api_version": "1.0",
  "form_id": 123456789,
  "campaign_id": 987654321,
  "google_key": "<the Key the tenant entered in Google Ads UI>",
  "is_test": false,
  "gcl_id": "..."
}
```

Validation: compare `google_key` against the per-tenant secret we issued. Reject on mismatch.

## Plan

### 1. DB migration — store the per-tenant webhook secret

Add to `tenant_business_profiles` (already holds `owner_phone`, lives 1:1 per tenant):

- `google_ads_webhook_key VARCHAR(64)` — nullable, plaintext (low blast radius — knowing it just lets you forge a lead row, no PII access)

Alembic revision: `add_google_ads_webhook_key.py`.

### 2. New route file — `app/api/routes/google_ads_webhooks.py`

```
POST /api/v1/google-ads/lead/{tenant_id}
```

Handler:

1. Load `TenantBusinessProfile` for `tenant_id` → 404 if missing.
2. Parse JSON body. Compare `body["google_key"]` against `profile.google_ads_webhook_key`. Reject 401 on mismatch or if key not configured.
3. Short-circuit if `body.get("is_test")` is True — log + 200 with `{"status":"test_received"}`.
4. Flatten `user_column_data` into a dict keyed by `column_id` (or `column_name` fallback).
5. Build the lead:
   - `name` ← `FULL_NAME` (or `FIRST_NAME` + `LAST_NAME`)
   - `email` ← `EMAIL`
   - `phone` ← `PHONE_NUMBER`, normalized via `app.core.phone.normalize_to_e164`
   - `extra_data` ← `{"source": "google_ads", "ad title": <campaign/form name if available>, "google_lead_id": ..., "form_id": ..., "campaign_id": ..., "gcl_id": ..., "raw_fields": {...all flattened qualifying questions...}}`
   - Audience-relevant qualifying-question answers (e.g. "What age?" → "Child" / "Adult") get copied to top-level keys `infer_audience` reads (`ad title`, `type of lessons`, or `class code`) so existing drip routing works without changes.
6. Dedup: if a lead already exists with same tenant_id + phone (or email) within last 24h, update extra_data instead of creating a new row.
7. Tag the lead via `LeadTagger` (existing service — picks audience pill).
8. Enroll in drip via `DripCampaignService.enroll_lead(tenant_id, lead.id, campaign_type=detect_campaign_type(...))`. Skips silently if drip disabled / lead has no phone / phone is existing customer.
9. Fire `notify_high_intent_lead(tenant_id, lead, conversation_id=None, source="google_ads")` so owner gets the hot-lead SMS.
10. Return `{"status": "ok", "lead_id": lead.id}`.

Mount in `app/api/routes/__init__.py`.

### 3. Admin endpoint — generate / rotate the key

`POST /api/v1/admin/tenants/{tenant_id}/google-ads/rotate-key` (admin or tenant_admin role) → generates a `secrets.token_urlsafe(36)` (≤50 chars to fit Google's UI limit), stores on `tenant_business_profiles`, returns the new key once. Existing key is overwritten — mention that in the response so the operator knows to update Google Ads.

### 4. Smoke test endpoint (optional)

Google Ads UI has a "Send test data" button. Make sure step 3 (`is_test: true`) returns 200 quickly so the UI shows green.

### 5. Frontend (later — not blocking tenant 3)

Settings → Integrations → "Google Ads" panel showing the webhook URL + a "Generate Key" / "Rotate Key" button. Out of scope for first cut; for tenant 3 we can hand them the URL + key over Slack.

## Drip campaigns — what's needed for tenant 3

The campaigns are already configured. Verified:

- **Campaign 1 — "Kids Registration Drip"** (id 1, `campaign_type='kids'`)
  - 4 steps: 10 min → 24 h → 48 h → 5 d
  - Step 4 has `check_availability=true` (queries Jackrabbit before sending)
- **Campaign 2 — "Adults Registration Drip"** (id 2, `campaign_type='adults'`)
  - 4 steps: 10 min → 24 h → 48 h → 5 d
  - Step 3 has `check_availability=true`

Both have full `message_template` text. Both have `is_enabled = false`.

**Action needed before going live:**

1. Flip `is_enabled = true` on both rows for tenant 3.
2. Confirm step 4 of campaign 1 / step 3 of campaign 2 pass — they call `DripMessageService.render_with_availability` which hits Jackrabbit. Tenant 3 has Jackrabbit `org_id=545911` and both API keys, so this should work, but worth a one-shot test.
3. Confirm `tenant_sms_configs` for tenant 3 has `is_enabled=true` and SMS isn't gated by an unfinished 10DLC campaign.
4. Confirm at least one `response_templates` entry exists on each campaign so inbound replies don't break (`handle_response` gracefully short-circuits if missing, but no replies fire either).

Routing into the right campaign happens automatically via `DripCampaignService.detect_campaign_type` — it reads `extra_data.ad title` / `lesson type` / `class code`. The Google Ads webhook handler maps qualifying-question answers into those keys (step 5 above).

## Open questions

- **Phone format**: Google Ads usually sends `PHONE_NUMBER` in E.164 already, but not guaranteed. Use `normalize_to_e164` and reject leads with no usable phone (still store, just skip drip).
- **Owner notification dedup**: existing `notify_high_intent_lead` already dedups within a window via `extra_data.conversation_id`. For google_ads leads we'll key on `google_lead_id` instead.
- **Multiple Google Ads accounts per tenant**: out of scope. One webhook URL + one key per tenant. If a tenant runs two ad accounts, both POST to the same endpoint — fine.

## Test plan

- [ ] Migration applies cleanly on staging
- [ ] Generate a key for tenant 3, paste into Google Ads sandbox, click "Send test data" — endpoint returns 200, no row created (because `is_test`)
- [ ] Curl-simulate a real payload (`is_test: false`) — Lead row created, audience tagged correctly for both kid + adult fixtures
- [ ] Drip enrollment fires, first SMS lands at the +1 number (use a tenant-3 test number, not Ashley's real one)
- [ ] Owner SMS notification fires to `2816278851`
- [ ] Bad `google_key` returns 401, no row created
- [ ] Missing/disabled drip campaigns: lead still stored, no enrollment, no error

## Rollout checklist (tenant 3)

1. Merge + deploy webhook code + migration
2. Run rotate-key endpoint for tenant 3 → record key in 1Password
3. In Google Ads UI: paste webhook URL + key, click "Send test data"
4. Flip both drip campaigns `is_enabled = true`
5. Verify SMS config + 10DLC status
6. Live test with one real lead before handing off to Ashley
