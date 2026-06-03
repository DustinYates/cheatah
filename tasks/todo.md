# Fix: follow-up worker leaves "sent but empty" orphan leads

## Problem
`app/workers/followup_worker.py` commits `followup_sent_at` BEFORE sending the SMS
and storing the outbound message. If `send_sms()` throws (any non-opt-out error) or
`add_message()` throws, the task 500s → Cloud Tasks retries → retry sees
`followup_sent_at` already set → skips. Result: lead permanently shows "sent" but the
conversation has zero messages (red "needs follow-up" dot, no record of contact).
~16 leads affected since Feb; spike of 8 on 2026-06-01 (tenants 3 + 330).

## Root cause
"Claim-before-work" hazard: the durable done-marker is written before the work that
can fail, and the same marker blocks the retry that should recover it.

## Fix: lease pattern (preserve double-send protection, allow recovery)
- [ ] Add `followup_in_progress_at` lease marker (lives in JSON `extra_data`, no migration)
- [ ] Atomic claim sets the LEASE (not `followup_sent_at`): match only if not already
      sent AND (no lease OR lease older than TTL). rowcount==0 → skip.
- [ ] Set `followup_sent_at` only AFTER `send_sms()` returns successfully (own commit,
      immediately, to shrink the crash window).
- [ ] Wrap `add_message()` in try/except → best-effort. SMS already went out, so a
      store failure must NOT fail the task or trigger a resend; just log it.
- [ ] On `send_sms()` failure (non-opt-out): clear the lease, then re-raise so the
      Cloud Tasks retry can genuinely re-attempt.
- [ ] Keep `RecipientOptedOutError` handling as-is (terminal skip); clear lease too.
- [ ] Keep existing `followup_sent_at` readers intact (leads.py:784, followup_service
      :96/:218, worker line 62) — semantics unchanged: still "done, don't resend".

## Lease TTL
- [ ] Conservative TTL (10 min) so duplicate tasks during a normal sub-second send can't
      double-claim, but a crashed attempt eventually frees for retry.

## Verify
- [ ] `uv run pytest` (follow-up worker tests)
- [ ] Re-read diff: `followup_sent_at` only reachable after a successful send; every
      failure path either clears the lease or is best-effort.
- [ ] No aware/naive datetime regression (SQL computes `updated_at` as naive UTC).

## Out of scope (separate, needs Telnyx delivery logs)
- Backfill/recovery of the ~16 existing orphans — NOT auto-re-triggered here (some may
  already have been texted; only Telnyx logs disambiguate). Handle as a follow-up.

## Review
Done. Root cause confirmed by reading the worker: `followup_sent_at` was committed
by the atomic claim BEFORE send/store, and the same marker blocked the recovery retry.

Code (`app/workers/followup_worker.py`):
- New `FOLLOWUP_LEASE_TTL = 10 min`.
- Claim now writes `followup_in_progress_at` (lease), matching only if not already
  sent AND no live lease. Lexicographic `<` on canonical UTC ISO strings = correct
  chronological compare (verified against real Postgres).
- `_mark_followup_sent()` sets `followup_sent_at` + drops the lease — called only
  after `send_sms()` succeeds, own commit, before anything else that can fail.
- `add_message()` is now best-effort (try/except) — SMS already sent, so a store
  failure must not fail the task or resend.
- Non-opt-out `send_sms()` failure → `_release_followup_lease()` then re-raise, so the
  Cloud Tasks retry can genuinely re-send.
- Existing `followup_sent_at` readers unchanged (semantics still "done, don't resend").

Dupe-text safety (per user requirement "ensure we don't send dupe texts"): send
failures are now classified by what we can prove about delivery —
- `RecipientOptedOutError` → not delivered → release lease + skip.
- `httpx.HTTPStatusError` (Telnyx 4xx/5xx, only queues on 2xx) → not delivered →
  release lease + re-raise so Cloud Tasks retries a real send (no dupe).
- ambiguous (timeout/connection drop = maybe delivered) → do NOT retry; mark sent +
  return "uncertain" + log for manual verification (never double-texts).
Plus: after a successful send the worker never returns non-2xx (mark + store are
best-effort), so a Cloud Tasks retry can't re-send. Concurrent dispatch is serialized
by the atomic lease claim. Net dupe vectors closed: concurrent dispatch, retry-after-
partial-failure, retry-after-ambiguous-send.

Tests (`tests/test_followup_worker.py`, all DB/providers mocked — matches codebase
convention): 5 tests lock in the contract (Telnyx-rejection releases lease + retries;
ambiguous-send marks sent + no retry; store-fail best-effort; happy path marks-then-
stores; lost claim skips). All pass. Raw SQL (jsonb_set / `- key` / lease cutoff)
validated against real Postgres.

Bonus root-cause fix (`tests/conftest.py`): added an autouse fixture that disposes the
global async engine after each test. The suite had a latent event-loop-leak flake —
a pooled asyncpg connection reused across pytest-asyncio per-test loops threw
"Future attached to a different loop" and failed whichever test reused it, purely by
collection order. Adding this test file shifted order and exposed it. Disposing the
pool per test makes the suite order-independent.

Full suite: 4 failed (all pre-existing/unrelated: 3× send_registration_link, 1×
promise_fulfillment dedup — fail identically on baseline), 318 passed (314 + my 4),
4 skipped. Zero regressions.

NOT deployed — needs a Cloud Run deploy to take effect. Backfill of the ~16 existing
orphans deferred (needs Telnyx delivery logs to know who was actually texted).
