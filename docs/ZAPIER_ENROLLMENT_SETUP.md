# Zapier Enrollment Auto-Tag Setup

When a customer enrolls in Jackrabbit, ConvoPro can automatically:

- Move the matching lead to the **"Registered"** pipeline stage
- Add an **`enrolled`** custom tag
- Append the enrollment details to the lead history
- Send an in-app notification to the tenant's admins

This is wired up via Zapier — each tenant creates a Zap in their own Zapier
account that fires when Jackrabbit records a new enrollment.

## Endpoint

`POST https://chattercheatah-900139201687.us-central1.run.app/api/v1/zapier/enrollment/{tenant_id}`

The `{tenant_id}` is the ConvoPro tenant DB id (Cypress-Spring = `3`,
Atlanta = `237`, Raleigh = `330`).

The endpoint always returns HTTP 200 with one of these statuses:

- `registered` — lead matched and tagged
- `already_processed` — same `enroll_id` already recorded (idempotent)
- `no_lead_match` — no lead found with this phone or email (the customer
  may have walked in without contacting ConvoPro first; nothing else to do)
- `ignored` — payload had no phone or email to match against

## Zap Configuration

### 1. Trigger

- **App:** Jackrabbit Class
- **Trigger event:** "New Enrollment" (or "Class Enroll" — depends on the
  Jackrabbit Zapier app version)

### 2. Action

- **App:** Webhooks by Zapier
- **Action event:** POST
- **URL:** `https://chattercheatah-900139201687.us-central1.run.app/api/v1/zapier/enrollment/<TENANT_ID>`
- **Payload Type:** `json`
- **Wrap Request In Array:** No
- **Unflatten:** Yes
- **Data Pass-Through?:** Yes (sends every Jackrabbit field — recommended
  so the endpoint can fuzzy-match without exact key configuration)

### 3. Fields

The endpoint accepts any of these field names (case-insensitive, dashes and
spaces normalized to underscores):

| Purpose | Accepted keys |
|---------|---------------|
| Enrollment ID (for dedup) | `enroll_id`, `enrollment_id`, `class_enroll_id`, `id` |
| Family ID | `family_id`, `jackrabbit_id`, `fam_id`, `jr_id` |
| Phone (for lead matching) | `phone_number`, `phone`, `home_phone`, `cell_phone`, `mobile`, `contacts_home_phone` |
| Email (for lead matching) | `email`, `email1`, `email_address`, `students_email` |
| Student name | `student_name`, `students_first_name`, `first_name` |
| Class name | `class_name`, `class`, `class_title` |
| Enrollment date | `enrollment_date`, `enroll_date`, `date_enrolled`, `start_date` |

If "Data Pass-Through" is on, no manual mapping is needed — Zapier sends every
field and we pick the ones we recognize.

## Per-Tenant Onboarding Steps

For each new BSS tenant:

1. Confirm `tenant_customer_service_configs` row exists for the tenant (it will
   if Jackrabbit `org_id` is already configured).
2. Tenant signs into their Zapier account and creates the Zap above with their
   tenant_id in the URL.
3. Test the Zap with a sample enrollment from Jackrabbit. Verify in ConvoPro
   that the lead's pipeline stage flipped to "Registered" and the `enrolled`
   tag was added.
4. Turn the Zap on.

## Optional: Signature Verification

The endpoint currently accepts unauthenticated POSTs (matching the existing
`/zapier/customer-update` and `/zapier/family-sync` pattern). If a tenant
needs HMAC verification:

1. Generate a random secret and store it in
   `tenant_customer_service_configs.zapier_callback_secret`.
2. In the Zap, add an `X-Zapier-Signature` header with the HMAC-SHA256 of the
   request body using the same secret.
3. (Endpoint code change required — verification is not currently wired up.)

## Behavior Notes

- **Lead matching:** by phone (E.164) or email, scoped to the tenant. Most
  recently created lead wins if multiple match.
- **Idempotency:** repeated webhook fires with the same `enroll_id` are no-ops.
- **Multi-student families:** each enrollment is appended to
  `extra_data.enrollments`, so siblings are tracked separately on the same
  lead.
- **No lead match:** logged + 200 returned. We don't create a phantom lead.
