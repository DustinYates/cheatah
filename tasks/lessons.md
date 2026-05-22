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
ORM — masking the fact that they're wrong. The crash only appears when the column is
put **explicitly in the SET clause** of a Core `update().values(...)` or a raw `text()`
UPDATE, which bypass `onupdate` and hand the aware value straight to the driver.

**Rules:**
1. When writing a timestamp via **Core `update().values()`** or **raw `text()` SQL**,
   never pass `datetime.now(timezone.utc)`. Either:
   - omit `updated_at` and let the model's `onupdate=datetime.utcnow` populate it, or
   - compute it naive: `datetime.now(timezone.utc).replace(tzinfo=None)`, or in SQL
     `(now() AT TIME ZONE 'utc')`.
2. This codebase stores **naive UTC** in all `created_at`/`updated_at`/`*_at` DateTime
   columns (CLAUDE.md convention). ORM hides aware/naive mismatches; Core/raw SQL does not.
3. **Verify a hotfix against real column types before deploying.** A 30-second
   `information_schema.columns` check (or running the worker once) would have caught this.
   Don't deploy a DB-write fix to a background worker without exercising the write path.
4. If you make the same class of fix in a second place, re-audit the first — the bug
   you're copying may be the bug.

**Recovery note:** background-worker tasks retry via Cloud Tasks (`maxAttempts: 100`,
`maxBackoff: 3600s`), so a crashing worker silently piles up a backlog that **blasts all
at once** when the bug is fixed. Before deploying a fix for a long-broken worker, decide
what to do with the queued backlog (`sms-processing` is shared across all tenants).
Purging it is a human-in-the-loop action (the safety layer blocks agent-initiated mass
deletion of shared jobs — by design).
