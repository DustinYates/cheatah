# Lessons

Patterns captured after corrections, to avoid repeating mistakes.

---

## Aware datetimes crash Core/raw-SQL writes to naive timestamp columns (2026-05-22)

**Mistake:** Two "duplicate prevention" atomic-claim fixes (drip `524031f`, follow-up
`b4100af`) wrote `datetime.now(timezone.utc)` (timezone-**aware**) to `updated_at`,
which is `TIMESTAMP WITHOUT TIME ZONE` (naive). asyncpg's `timestamp_encode` then
raises `can't subtract offset-naive and offset-aware datetimes`, 500-ing the worker on
its first DB write. Result: **drip dead ~7 days, email follow-up dead ~4 days, in prod.**
I shipped the same bug twice and didn't catch it until the tenant reported silence.

**Why it slipped through:** ORM attribute assignment (`obj.updated_at = aware_dt`) had
always *looked* fine because the model column has `onupdate=datetime.utcnow` (naive),
which overrides the aware value on flush. So aware datetimes "work" everywhere via the
ORM — but ONLY because `onupdate=datetime.utcnow` (naive) fires when the column is NOT
explicitly set. The crash appears whenever the aware value reaches the column: a Core
`update().values(...)`, a raw `text()` UPDATE, **or an explicit ORM assignment**
(`obj.updated_at = datetime.now(timezone.utc)`, which bypasses `onupdate`). Columns with
**no `onupdate`** (e.g. `drip_enrollments.next_step_at`) crash unconditionally.

**This bit twice in one session:** my first fix patched only the `.values()` CAS and
missed the ORM `enrollment.updated_at = ...` / `next_step_at = ...` assignments — so the
drip then fired a lead's entire 4-step sequence in 15s (post-CAS crash → Cloud Tasks
retry → each retry advanced+sent a step).

**Rules:**
1. Use naive UTC for **every** datetime written to a naive column, regardless of path
   (Core `.values()`, raw SQL, OR ORM attribute assignment): `datetime.now(timezone.utc).replace(tzinfo=None)`
   in Python, `(now() AT TIME ZONE 'utc')` in SQL. A `_naive_utcnow()` helper keeps it DRY.
2. This codebase stores **naive UTC** in all `*_at` DateTime columns (CLAUDE.md). Do NOT
   assume the ORM saves you — `onupdate` only fires when the column isn't explicitly set.
3. When fixing, grep for **all** writes to the column (`= datetime.now(timezone.utc)`
   assignments too), not just `.values(`. The bug you're copying may be the bug.
4. **Cascade trap:** an atomic CAS that commits the advance *separately, before* a later
   commit that crashes turns one crash into a runaway — each Cloud Tasks retry advances.
5. **Verify a worker DB-write hotfix end-to-end before declaring done** — trigger the
   endpoint with a throwaway 555-number lead and confirm the DB state, not just "no error".

**Recovery note:** background-worker tasks retry via Cloud Tasks (`maxAttempts: 100`,
`maxBackoff: 3600s`), so a crashing worker silently piles up a backlog that **blasts all
at once** when the bug is fixed. Before deploying a fix for a long-broken worker, decide
what to do with the queued backlog (`sms-processing` is shared across all tenants).
Purging it is a human-in-the-loop action (the safety layer blocks agent-initiated mass
deletion of shared jobs — by design).
