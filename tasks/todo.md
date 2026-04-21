# Billing v2 — Stripe ACH + Self-Serve Plans

**Origin:** support request from Ashley (BSS Cypress-Spring) — needs a way to enter payment method (ACH preferred) and select/upgrade plan.

## Decisions locked

- **Stripe Financial Connections** for ACH (built into Stripe, no Plaid SDK)
- **Stripe Checkout** (hosted) for upgrade flow
- **Stripe Customer Portal** for managing payment methods + canceling
- **One Stripe customer per tenant**; only `tenant_admin` can upgrade
- **Plans defined in Stripe** (not hardcoded). Limits sync via Price metadata.
- `sms_limit` counts **messages** (not conversations)
- **Lite tier:** 30-day trial via `trial_period_days=30`
- **Payment failure:** `past_due` → email owner → auto-disable on `customer.subscription.deleted` (Stripe handles retry exhaustion)

## Stripe Price IDs (test mode — created)

| Tier | Price ID | $/mo | sms_limit | call_minutes_limit | Trial |
|------|----------|------|-----------|-------------------|-------|
| `lite` | `price_1TOSLY53WQv4UTA7RKQNRytb` | $30 | 0 | 0 | 30d |
| `starter` | `price_1TOSLZ53WQv4UTA79w1di8UD` | $99 | 1000 | 0 | — |
| `essentials` | `price_1TOSLa53WQv4UTA72gvrUDON` | $249 | 1500 | 200 | — |
| `growth` | `price_1TOSLb53WQv4UTA7P1RMQXPZ` | $399 | 2000 | 400 | — |

Each Price has `tier`, `sms_limit`, `call_minutes_limit`, `trial_days` metadata so the webhook can sync limits without a hardcoded map.

## Backend tasks

- [ ] Alembic migration: add to `tenants` — `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`, `current_plan_price_id`, `current_period_end`
- [ ] Update `Tenant` model in `app/persistence/models/tenant.py`
- [ ] `app/settings.py`: add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PORTAL_RETURN_URL`
- [ ] New service `app/domain/services/billing_service.py`:
  - `get_or_create_customer(tenant)` — create Stripe customer, persist `stripe_customer_id`
  - `create_checkout_session(tenant, price_id)` — returns Checkout URL; pass `subscription_data.trial_period_days` from Price metadata
  - `create_portal_session(tenant)` — returns Customer Portal URL
  - `sync_subscription_to_tenant(subscription)` — read price metadata, update `tier` / `sms_limit` / `call_minutes_limit` / `subscription_status` / `current_period_end`
  - `list_active_plans()` — fetch active Prices from Stripe (cache 5min)
- [ ] New routes `app/api/routes/billing.py`:
  - `GET /api/v1/billing/plans` — list active plans (auth: any tenant user)
  - `GET /api/v1/billing/subscription` — current tenant subscription state
  - `POST /api/v1/billing/checkout-session` — body `{price_id}`, returns `{url}` (auth: tenant_admin)
  - `POST /api/v1/billing/portal-session` — returns `{url}` (auth: tenant_admin)
  - `POST /api/v1/billing/webhook` — Stripe webhook (no auth, signature-verified)
- [ ] Webhook handlers (in priority order):
  - `customer.subscription.created` → set `subscription_status='active'|'trialing'`, sync limits
  - `customer.subscription.updated` → sync limits + status (handles plan changes)
  - `customer.subscription.deleted` → set `subscription_status='canceled'`, downgrade to disabled tier (`tier='disabled'`, sms/calls = 0)
  - `invoice.payment_failed` → set `subscription_status='past_due'`, send SMS + email to tenant owner
  - `invoice.payment_succeeded` → log only (subscription.updated handles state)
- [ ] Notification helper for past_due — reuse `notifications.py` patterns; subject "Payment failed for ConvoPro subscription"

## Frontend tasks

- [ ] `client/src/api/client.js`: add `getPlans()`, `getSubscription()`, `createCheckoutSession(priceId)`, `createPortalSession()`
- [ ] Extend [client/src/pages/UsageBilling.jsx](client/src/pages/UsageBilling.jsx) (don't create a new page — keep it under existing `/billing` route):
  - **Current Plan card:** tier badge, status (`active`/`trialing`/`past_due`/`canceled`), `current_period_end` ("Renews on …" or "Trial ends on …"), "Manage subscription" button → portal
  - **Payment Method card:** brand + last4 (from `subscription.default_payment_method`) OR "No payment method on file" + "Add payment method" → portal
  - **Past-due banner** (red) when `subscription_status='past_due'`: "Payment failed — update your payment method to avoid service interruption"
  - **Available Plans grid:** 4 cards from `/billing/plans`, current plan disabled/labeled "Current", others show "Select" → opens Checkout in same tab
- [ ] Handle return from Checkout: `?session=success` → toast + refetch subscription; `?session=cancel` → silent

## Testing checklist

- [ ] Run `uv run alembic upgrade head` against local DB
- [ ] Stripe CLI: `stripe listen --forward-to localhost:8000/api/v1/billing/webhook` — copy whsec_ to `STRIPE_WEBHOOK_SECRET`
- [ ] Self-serve subscribe to Lite as tenant 3 — verify trial start, tenant row updated
- [ ] Stripe CLI: `stripe trigger invoice.payment_failed` → verify past_due banner + email
- [ ] Subscribe to Growth via Checkout with Stripe test ACH (`pm_usBankAccount_success`) — verify limits update to 2000/400
- [ ] Upgrade Lite → Essentials via Customer Portal — verify webhook updates tier
- [ ] Cancel via Portal → verify auto-disable

## Out of scope (v3)

- Metered/overage billing (charge for SMS over `sms_limit`)
- Per-seat pricing
- Annual plans / discounts
- Tax (enable Stripe Tax in Dashboard later, no code change)
- In-app invoice history (Customer Portal handles for now)

## Production cutover

1. Create Products/Prices in Stripe **live** mode (re-run `scripts/stripe_setup_plans.py` with live key)
2. Update GCP Secret Manager: `STRIPE_SECRET_KEY` (live), `STRIPE_WEBHOOK_SECRET` (live)
3. Update `STRIPE_PORTAL_RETURN_URL` to prod URL
4. Configure live webhook in Stripe Dashboard → `https://chattercheatah-…run.app/api/v1/billing/webhook`
5. Replace test Price IDs in any hardcoded references (none expected — we read from Stripe)
6. **Rotate the test key** that was leaked in chat

---

## Review

_(populated after implementation)_
