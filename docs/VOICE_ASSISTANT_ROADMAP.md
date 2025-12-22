# Voice Calls Roadmap for Chatter Cheetah (Twilio, 1 number per tenant)

## Guiding Recommendations (Baked into Phases)

- Start with Twilio-native voice loop (fastest to ship, lowest engineering risk).
- Optimize for latency + short turns (voice UX fails when responses are long).
- Default to persist summaries, not full transcripts (store recordings separately with access controls).
- Build handoff + business-hours routing early (non-negotiable for real tenants).
- Treat ElevenLabs as a later "premium voice" upgrade once call flow is stable.

---

## Phase 0 — Telephony Foundation (Numbers, Routing, Logging)

**Goal**: Every tenant can forward calls to their dedicated Twilio number; calls are logged reliably.

### Build

- Provision one Twilio number per tenant (store mapping).
- Twilio inbound webhook → your FastAPI (Cloud Run).
- Business-hours routing:
  - open: AI answers (placeholder message in Phase 0 is fine)
  - closed: voicemail or "leave details" capture
- Call recording ON (Twilio recording enabled per call).
- Minimal DB:
  - `calls` table: `tenant_id`, `call_sid`, `from/to`, `start/end`, `status`, `duration`, `recording_sid/url` placeholder.

### Exit Criteria

- Tenant forwards their business number → Twilio tenant number.
- Inbound calls create a `calls` row and recording metadata.

---

## Phase 1 — MVP AI Receptionist (Lead Capture + Summaries)

**Goal**: AI can answer, capture intent + details, create/update lead/contact, and write a summary to the user profile.

### Build

- Use Twilio-native voice assistant flow (e.g., Twilio ConversationRelay / equivalent Twilio conversational pattern).
- Core intents (minimum):
  - pricing/info, hours/location, booking request, support request, wrong number/spam
- Structured capture:
  - name, phone, email (if offered), reason for calling, urgency, preferred callback time
- Persistence:
  - Create/update Contact/Lead in your existing system
  - Save call summary (not full transcript) to profile:
    - `call_summaries`: `call_id`, `contact_id/lead_id`, `intent`, `outcome`, `summary_text`, `extracted_fields` (json)
- UI:
  - Calls list (basic)
  - Contact profile "Calls" panel showing summary + recording link
- Guardrails:
  - short responses only
  - no payments, no sensitive promises, no legal/medical

### Exit Criteria

- Tenants can use it after-hours to reliably capture leads.
- Calls produce a summary attached to the correct profile.

---

## Phase 2 — Handoff + Onboarding Options (Operational Readiness)

**Goal**: Tenants can configure what happens when AI can't/shouldn't handle the call.

### Build

- Onboarding configuration (per tenant):
  - business hours
  - handoff mode(s):
    - live transfer number
    - "take a message + notify"
    - schedule callback
  - escalation rules (caller asks for human, repeated confusion, high-value intent)
  - default greeting + disclosure line (recording notice)
- Notifications:
  - Email/SMS/inside-app notification to tenant user(s) with call summary + recording link
- Better call outcomes tracking:
  - `outcome` enum: `lead_created`, `booked_requested`, `transferred`, `voicemail`, `dismissed`
- Reliability:
  - retries/idempotency for Twilio webhooks
  - rate limits / abuse controls

### Exit Criteria

- Tenants can choose handoff behavior during onboarding.
- Escalations happen predictably and are auditable.

---

## Phase 3 — Performance + Voice Quality Upgrades (Optional ElevenLabs Track)

**Goal**: Reduce "robotic" feel and improve responsiveness, without destabilizing production.

### Build

- Latency optimization (regardless of TTS vendor):
  - enforce "1–2 sentences + a question" response policy
  - streaming responses end-to-end (where supported)
  - interrupt handling (barge-in)
- Add tenant-level tuning:
  - max response length / max tokens per turn
  - speaking speed / tone style
  - pronunciation dictionary (business name, staff names)
- Optional premium voice path:
  - ElevenLabs as a configurable TTS provider only after you have stable call flows
  - A/B compare: Twilio-native TTS vs ElevenLabs on real calls
  - Keep as "feature flag" per tenant/tier

### Exit Criteria

- Noticeable drop in latency complaints and "robotic" feedback.
- If ElevenLabs enabled: stable, measurable quality improvement.

---

## Phase 4 — Conversions + Tooling (Booking, Integrations, Analytics)

**Goal**: Move beyond receptionist into revenue-driving automation.

### Build

- Booking workflow:
  - appointment request capture → tenant scheduling integration (or your own scheduling module)
  - confirmations via SMS/email
- CRM-style enrichment:
  - tag leads by intent, urgency, service requested
  - follow-up tasks
- Analytics dashboard:
  - call volume, missed calls, handoff rate, lead conversion, avg latency proxy, drop rate
- Compliance hardening:
  - retention policies per tenant
  - role-based access to recordings
  - transcript storage optional with explicit opt-in

### Exit Criteria

- Tenants see measurable reduction in missed-call loss and improved lead handling.

---

## Implementation Order (Practical)

1. **Phase 0** (numbers + forwarding + recording + call logs)
2. **Phase 1** (AI receptionist + summaries into profiles)
3. **Phase 2** (handoff + onboarding options)
4. **Phase 3** (latency/voice polish; optionally ElevenLabs)
5. **Phase 4** (booking + integrations + analytics)

