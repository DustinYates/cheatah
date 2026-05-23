# Incident & Change Log — Drip + Email Follow-up Outage (2026-05-22)

Reference for what changed, why, and how to undo it. Tenant 3 (BSS Cypress-Spring) was the
reporter; the core bug was global (all tenants).

## TL;DR
The SMS **drip campaign** (dead since ~May 15) and the **email→SMS follow-up** (dead since
~May 18) both stopped sending. Root cause: timezone-**aware** `datetime.now(timezone.utc)`
values written to **naive** (`TIMESTAMP WITHOUT TIME ZONE`) columns, which makes asyncpg
raise `can't subtract offset-naive and offset-aware datetimes` and 500s the worker. Fixed
across the commits below, verified live, and the live revision is healthy.

## Timeline of the bug
- `524031f` (May 15) — added the drip atomic step-claim. Introduced the tz bug in the drip
  worker → every drip step 500'd → all enrollments stuck at step 0.
- `b4100af` (May 18) — added the follow-up atomic claim. Same tz bug → every follow-up 500'd.
  Last successful follow-up: Leslie Dimas, May 18 16:38 UTC.
- May 22 — tenant 3 reported "no automation + still says enrolled in drip." Diagnosed & fixed.

## Root cause (full)
`*_at` columns in this codebase are **naive UTC** (CLAUDE.md convention). An aware datetime
reaches the driver and crashes via ANY path:
- Core `update().values(updated_at=<aware>)`
- raw `text()` UPDATE setting `updated_at = <aware bind>`
- **ORM explicit assignment** `enrollment.updated_at = <aware>` (bypasses the column's
  `onupdate=datetime.utcnow`, which only fires when the column is NOT explicitly set)
- columns with **no `onupdate`** (`drip_enrollments.next_step_at`) crash unconditionally

The drip cascade (see Mary Obadan below) was a second-order effect: the atomic claim commits
the step advance **separately, before** a later commit that crashed → Cloud Tasks retried →
each retry advanced + sent the next step.

## Commits (what & why)
| Commit | What | Why |
|--------|------|-----|
| `327e8c3` | Drip CAS: drop `updated_at` from `.values()`. Follow-up CAS: compute `updated_at` via SQL `(now() AT TIME ZONE 'utc')`. | First fix. **Incomplete for drip** — only patched `.values()`, missed the ORM assignments. |
| `313e87b` | `client/src/utils/timelineTransform.js` — label email timeline events by `lead.extra_data.email_subject` instead of hardcoded "Get In Touch Form Submission". | Booking-page captures were mislabeled. Frontend only. |
| `1a37032` | `tasks/lessons.md` created. | Capture the lesson. |
| `60c6f97` | **Complete drip fix.** Added `_naive_utcnow()` helper; used it for all 7 `enrollment.updated_at` / `next_step_at` writes in `drip_campaign_service.py`. | The 6 ORM assignments `327e8c3` missed → drip cascade. |
| `2effb96` | Corrected `tasks/lessons.md` (ORM assignment crashes too; cascade trap). | My first mental model was wrong. |

## Deployments (Cloud Run service `chattercheatah`, project `chatbots-466618`)
- `00865-gj8` — after `327e8c3` (tz fix)
- `00866-ztw` — after `313e87b` (mislabel fix; also carries tz fix)
- `00867-gh2` — after `60c6f97` (complete drip fix). **CURRENT / healthy.**

## Manual DB changes made (NOT in code — record for audit)
1. **Purged the `sms-processing` Cloud Tasks queue** (~173 stale drip+followup tasks, all
   tenants). Run by the user (human-in-the-loop; agent purge of shared queue is blocked by
   design). Effect: the ~173 backlogged messages were dropped ("fix forward only" — chosen to
   avoid blasting days-old leads). ~68 follow-up leads from May 18–22 will NOT get their
   (now-stale) follow-up; they still carry `followup_scheduled=true / followup_sent_at=null`
   internally. Not user-visible.
2. **Cancelled 59 orphaned tenant-3 drip enrollments** stuck at step 0:
   `UPDATE drip_enrollments SET status='cancelled', cancelled_reason='system_cleanup_tz_bug_2026-05-22' WHERE tenant_id=3 AND status='active' AND current_step=0 AND next_task_id IS NULL`
   and set `extra_data.drip_enrolled=false` on those 59 leads. So the dashboard stops showing
   them as actively enrolled. (To find them later: `cancelled_reason='system_cleanup_tz_bug_2026-05-22'`.)
3. **Marked enrollment 97 (Mary Obadan, lead 3003) `completed`** to stop its crash-retry loop.
4. Test leads/enrollments created and **deleted** during verification: leads 2996 & 3005,
   enrollment 98, plus their conversations/messages/opt-ins. Phone numbers used were fictional
   `+12815550147` / `+12815550148` (reserved 555-01xx range). All cleaned up (verified 0 left).

## Verification (live)
- Follow-up worker: POST `/workers/followup` for a throwaway 555 lead → `200 success`,
  `followup_sent_at` set, no tz error.
- Drip worker: POST `/workers/drip-step` for a throwaway step-0 enrollment → `200`, advanced
  to step 1, scheduled step 2 **+1 day** (delay respected, no cascade); set to step 4 → `200
  completed` (the exact write that crashed on Mary now commits cleanly).

## Known / open items (NOT fixed)
- **Telnyx storage echoes:** outbound drip/follow-up SMS get logged twice in the timeline (one
  `metadata=null` from our send + one `source=telnyx_ai_assistant` from the Telnyx conversation
  API via `ai-call-complete`). These are **display duplicates, not real double-sends.**
  Pre-existing; see MEMORY.md "Duplicate SMS Messages in Timeline" history.
- **Mary Obadan** received 4 rapid drip texts during the cascade (one-time; can't undo).
- ~68 May 18–22 leads won't get their purged follow-up (see DB change #1).

## If something regresses — where to look
- Drip not advancing / 500s on `/workers/drip-step` → check `drip_campaign_service.py` for any
  new aware-datetime write to a naive column (`= datetime.now(timezone.utc)`); use `_naive_utcnow()`.
- Follow-up 500s on `/workers/followup` → `followup_worker.py` CAS (`updated_at` must be SQL
  `(now() AT TIME ZONE 'utc')`, not a Python aware bind).
- Logs: `gcloud logging read '... severity=ERROR AND textPayload:"offset-naive"' --project chatbots-466618`.
- Rollback: `git revert 60c6f97 327e8c3` reverts the code, but reintroduces the tz crash —
  don't, unless replacing with another naive-datetime fix.
