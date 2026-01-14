# State Machine Diagrams

This document contains state machine diagrams for all stateful components in the ChatterCheetah system.

---

## 1. Call State Machine

Voice calls progress through these states based on Twilio webhook callbacks.

```mermaid
stateDiagram-v2
    [*] --> initiated: Inbound call received

    initiated --> ringing: CallStatus webhook
    initiated --> in_progress: Call answered

    ringing --> in_progress: Call answered
    ringing --> no_answer: No answer timeout
    ringing --> busy: Line busy
    ringing --> canceled: Caller hung up

    in_progress --> completed: Call ended normally
    in_progress --> failed: Call failed

    completed --> [*]
    failed --> [*]
    busy --> [*]
    no_answer --> [*]
    canceled --> [*]
```

**Transitions triggered by:** Twilio `CallStatus` webhook at `/voice/status`

**Key fields:**
- `started_at` - Set when entering `in_progress`
- `ended_at` - Set on terminal states
- `duration` - Calculated from start/end times
- `recording_url` - Captured after completion

---

## 2. Escalation State Machine

Escalations are triggered by explicit user requests, low AI confidence, or manual admin action.

```mermaid
stateDiagram-v2
    [*] --> pending: Escalation created

    pending --> notified: Admin notification sent
    pending --> cancelled: Admin cancels

    notified --> resolved: Admin resolves issue

    resolved --> [*]
    cancelled --> [*]
```

**Triggers:**
- `explicit_request` - User says "speak to human", "agent", "manager", etc.
- `low_confidence` - LLM confidence score < 0.5
- `manual` - Admin creates escalation manually

**Notification methods:** Email, SMS, In-app notification

---

## 3. Lead State Machine

Leads are captured from conversations and can auto-convert to Contacts.

```mermaid
stateDiagram-v2
    [*] --> new: Lead captured

    new --> verified: Admin verifies lead
    new --> unknown: Cannot verify

    verified --> Contact: Auto-conversion\n(has name + email/phone)

    Contact --> [*]
    unknown --> [*]
```

**Auto-conversion criteria:**
- Lead has a non-empty name
- AND (has email OR has phone number)

**Sources:** `voice_call`, `sms`, `email`, `web_chat`

---

## 4. SMS Opt-In State Machine

Manages customer SMS consent for compliance (TCPA).

```mermaid
stateDiagram-v2
    [*] --> opted_out: Default state

    opted_out --> opted_in: Keyword opt-in\n(e.g., "SUBSCRIBE")
    opted_out --> opted_in: Manual opt-in
    opted_out --> opted_in: API opt-in

    opted_in --> opted_out: STOP keyword
    opted_in --> opted_out: Manual opt-out
    opted_in --> opted_out: API opt-out
```

**Tracking:**
- `opted_in_at` / `opted_out_at` timestamps
- `opt_in_method` / `opt_out_method` for audit

---

## 5. SMS Delivery State Machine

Tracks outbound SMS delivery status via Twilio callbacks.

```mermaid
stateDiagram-v2
    [*] --> queued: SMS sent to Twilio

    queued --> sent: Twilio sends to carrier
    queued --> failed: Send error

    sent --> delivered: Carrier confirms
    sent --> failed: Delivery failed

    delivered --> [*]
    failed --> [*]
```

**Stored in:** `Message.message_metadata` JSON field
- `twilio_message_sid`
- `delivery_status`
- `status_updated_at`

---

## 6. Prompt Bundle State Machine

AI prompt templates progress through draft → testing → production.

```mermaid
stateDiagram-v2
    [*] --> draft: Created

    draft --> testing: Ready for testing
    testing --> draft: Needs revision

    testing --> production: Promoted to live
    production --> draft: Rollback

    note right of production
        Only ONE production bundle
        per channel per tenant
    end note
```

**Channels:** `chat`, `voice`, `sms`, `email`

**Constraint:** Unique partial index ensures only one `production` bundle per channel per tenant.

---

## 7. Email Conversation State Machine

Tracks email thread status for the Gmail responder feature.

```mermaid
stateDiagram-v2
    [*] --> active: Email received

    active --> escalated: Trigger word detected\nor no-response timeout
    active --> spam: Marked as spam
    active --> resolved: Thread completed

    escalated --> resolved: Admin resolves
    escalated --> spam: Marked as spam

    resolved --> [*]
    spam --> [*]
```

**Escalation triggers:**
- Keywords: "urgent", "complaint", "lawyer", "legal"
- Auto-escalate after N hours without response (configurable)

---

## 8. Zapier Request State Machine

Tracks async Zapier webhook request/response lifecycle.

```mermaid
stateDiagram-v2
    [*] --> pending: Request sent

    pending --> completed: Response received
    pending --> timeout: Timeout elapsed
    pending --> error: Processing error

    completed --> [*]
    timeout --> [*]
    error --> [*]
```

**Request types:** `customer_lookup`, `customer_query`

**Tracking:** `correlation_id` (UUID) for request/response matching

---

## 9. Notification State Machine

Simple read/unread tracking for user notifications.

```mermaid
stateDiagram-v2
    [*] --> unread: Notification created

    unread --> read: User views notification

    read --> [*]
```

**Notification types:**
- `call_summary` - Call recording available
- `escalation` - Escalation alert
- `lead_captured` - New lead
- `handoff` - Transfer notification
- `voicemail` - Voicemail available
- `system` - System message
- `email_promise` - Promise fulfillment

**Priority levels:** `low`, `normal`, `high`, `urgent`

---

## 10. Call Summary Classification

Post-call AI classification of intent and outcome.

```mermaid
stateDiagram-v2
    state "Call Completed" as cc
    state "AI Analysis" as ai

    [*] --> cc: Call ends\n(duration > 5s)

    cc --> ai: Transcript analyzed

    state ai {
        state "Intent Classification" as intent
        state "Outcome Classification" as outcome

        [*] --> intent
        intent --> outcome

        state intent {
            pricing_info
            hours_location
            booking_request
            support_request
            wrong_number
            general_inquiry
        }

        state outcome {
            lead_created
            info_provided
            voicemail
            booking_requested
            transferred
            dismissed
        }
    }

    ai --> [*]
```

---

## 11. Contact State Machine

Contacts use soft-delete and merge patterns.

```mermaid
stateDiagram-v2
    [*] --> active: Contact created\n(or converted from Lead)

    active --> deleted: Soft delete\n(deleted_at set)
    active --> merged: Merged into\nanother contact

    deleted --> [*]
    merged --> [*]

    note right of merged
        merged_into_contact_id
        tracks destination
    end note
```

**Audit fields:**
- `deleted_at`, `deleted_by`
- `merged_at`, `merged_by`, `merged_into_contact_id`

---

## Summary Table

| Component | States | Primary Trigger |
|-----------|--------|-----------------|
| Call | initiated → ringing → in_progress → completed/failed/busy/no_answer/canceled | Twilio webhooks |
| Escalation | pending → notified → resolved/cancelled | Intent detection, keywords |
| Lead | new → verified → Contact | Info capture, auto-conversion |
| SMS Opt-In | opted_out ↔ opted_in | Keywords, manual, API |
| SMS Delivery | queued → sent → delivered/failed | Twilio status callbacks |
| Prompt Bundle | draft → testing → production | Manual promotion |
| Email Conversation | active → escalated → resolved/spam | Gmail events, triggers |
| Zapier Request | pending → completed/timeout/error | Webhook responses |
| Notification | unread → read | User action |
| Contact | active → deleted/merged | Admin action |

---

## File References

- **Models:** `app/persistence/models/`
- **Services:** `app/domain/services/`
- **Webhooks:** `app/api/routes/*_webhooks.py`
