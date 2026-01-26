# Telnyx Voice AI Agents Configuration

This document describes the Telnyx Voice AI agents configured for British Swim School.

## Overview

There are **TWO** voice agents configured:

| Agent | Language | Assistant ID | Phone | Purpose |
|-------|----------|--------------|-------|---------|
| **ChatterCheetah Voice BSS** | English | `assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d` | +1-281-626-0873 | Primary English assistant (routes Spanish to SP) |
| **ChatterCheetah Voice BSS SP** | Spanish | `assistant-109f3350-874f-4770-87d4-737450280441` | +1-281-767-9141 | Spanish-speaking assistant |

### Performance Metrics (Both Agents)
- **Estimated Voice Latency**: ~1350ms
- **Estimated Cost**: ~$0.082 per minute + telephony fees
- **Model**: google/gemini-2.5-flash
- **API Key**: gemvoice

---

## Agent 1: ChatterCheetah Voice BSS (English)

### Basic Info

- **Name**: ChatterCheetah Voice BSS
- **Assistant ID**: `assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d`
- **Created**: 12 Jan 2026 9:52 PM
- **Phone Number**: +1-281-626-0873

### Voice Configuration

| Setting | Value |
|---------|-------|
| Provider | Telnyx |
| Voice Model | NaturalHD |
| Voice | lyra |
| Voice Speed | 1 |
| Transcription Model | deepgram/nova-3 |
| Transcription Language | Auto (auto-detect) |
| Smart Format | Enabled |
| Numerals | Enabled |
| Noise Suppression | Enabled (Deepfilternet) |
| Attenuation Limit | 83 (max 0-100) |
| Advanced Mode | Enabled |
| Background Audio | Silence |
| Interruptions | Enabled |

**Speaking Plan Timings:**
- Wait Seconds: 0.1s
- On Punctuation: 0.1s
- On No Punctuation: 0.1s
- On Number: 0.1s

### Greeting Configuration

- **Mode**: Assistant speaks first
- **Message**: "Hi, I'm British Swim Schools A.I. Assistant. How can I help you?"

### Spanish Language Routing Logic

This agent implements a **critical language detection rule**:
```
IF transcript contains: spanish | espanol | español | "no english" | "don't speak english" | "only spanish"
   OR English confidence is low/unstable
THEN:
   Say: "Sure! one second"
   Invoke: Handoff tool
   Transfer to: "ChatterCheetah Voice BSS SP"
ELSE:
   Continue in English
```

### Tools Configured

1. **Handoff** - Routes to ChatterCheetah Voice BSS SP (Spanish)
2. **send_registration_link** - Webhook to send SMS registration links
3. **Send Message** - Send text messages to caller
4. **Hang Up** - End call when complete
5. **Transfer** - Transfer to staff at +1-281-601-4588

### Webhook: send_registration_link

| Setting | Value |
|---------|-------|
| URL | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/send-registration-link` |
| Method | POST |
| Request Mode | Async |

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `location` | string | Yes | Pool location: "Cypress", "Langham Creek", or "Spring" |
| `level` | string | Yes | Swim level (e.g., "Adult Level 3", "Tadpole") |
| `caller_phone` | string | No | Caller's phone number |

### Call Settings

| Setting | Value |
|---------|-------|
| Max Call Duration | 1800 seconds (30 min) |
| User Idle Timeout | 60 seconds |
| Voicemail Detection | Continue assistant |
| Channel Limit | 10 |
| AnchorSite | Latency |
| Record Outbound Calls | Do Not Record |
| Inbound Call Recording | Disabled |
| Support Unauthenticated Web Calls | Enabled |
| Conversation Inactivity | 10000000 minutes (disabled) |

### TeXML Configuration

- **Application Name**: `ai-assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d`
- **Application ID**: `2871678346117252267`
- **Outbound Voice Profile ID**: `2859607228711699732`

### Widget Configuration

```html
<telnyx-ai-agent agent-id="assistant-ed763aa1-a8af-4776-92aa-c4b0ed8f992d"></telnyx-ai-agent>
<script async src="https://unpkg.com/@telnyx/ai-agent-widget@next"></script>
```

---

## Agent 2: ChatterCheetah Voice BSS SP (Spanish)

This is the Spanish-speaking assistant that receives transfers from the English assistant when Spanish is detected.

**Transfer Trigger:** When the English assistant detects Spanish keywords, it:
1. Says "Sure! one second"
2. Invokes the Handoff tool to transfer to this agent

### Basic Info

- **Name**: ChatterCheetah Voice BSS SP
- **Assistant ID**: `assistant-109f3350-874f-4770-87d4-737450280441`
- **Created**: 17 Jan 2026 7:34 AM
- **Phone Number**: +1-281-767-9141

### Voice Configuration

| Setting | Value |
|---------|-------|
| Provider | Telnyx |
| Voice Model | NaturalHD |
| Voice | eris |
| Voice Speed | 1 |
| Transcription Model | deepgram/nova-3 |
| Transcription Language | Spanish (Latin America) |
| Smart Format | Enabled |
| Numerals | Enabled |
| Noise Suppression | Enabled (Krisp) |
| Background Audio | Silence |
| Interruptions | Enabled |

**Speaking Plan Timings:**
- Wait Seconds: 0s
- On Punctuation: 0.3s
- On No Punctuation: 0.2s
- On Number: 0.3s

### Tools Configured

1. **Transfer** - Transfer calls to staff at +1-281-601-4588
2. **Hang Up** - End call when conversation completes
3. **Send DTMF** - Send DTMF tones during calls
4. **Send Message** - Send SMS text messages to caller (post-call only)

### Call Settings

| Setting | Value |
|---------|-------|
| Max Call Duration | 1800 seconds (30 min) |
| User Idle Timeout | 60 seconds |
| Voicemail Detection | Continue assistant |
| Channel Limit | 10 |
| AnchorSite | Latency |
| Record Outbound Calls | Do Not Record |
| Inbound Call Recording | Enabled |
| Support Unauthenticated Web Calls | Enabled |
| Conversation Inactivity | Not configured |

### TeXML Configuration

- **Application Name**: `ai-assistant-109f3350-874f-4770-87d4-737450280441`
- **Application ID**: `2874870294063875315`
- **Outbound Voice Profile ID**: `2859607228711699732`

### Webhook Configuration

| Type | URL |
|------|-----|
| Delivery Status | `https://chatterchetah-900139201687.us-central1.run.app/api/v1/telnyx` |

### Widget Configuration

```html
<telnyx-ai-agent agent-id="assistant-109f3350-874f-4770-87d4-737450280441"></telnyx-ai-agent>
<script async src="https://unpkg.com/@telnyx/ai-agent-widget@next"></script>
```

---

## Key Differences Between Agents

| Feature | Agent SP (Spanish) | Agent EN (English) |
|---------|-------------------|-------------------|
| Primary Language | Spanish Only | English (Auto-detect) |
| Spanish Detection | N/A | Detects & routes to SP |
| Voice | eris | lyra |
| Transcription | Spanish (Latin America) | Auto (detect all) |
| Inbound Recording | Enabled | Disabled |
| Noise Engine | Krisp | Deepfilternet |
| Attenuation Limit | N/A | 83 |
| Advanced Mode | N/A | Enabled |
| Conversation Timeout | Not configured | 10000000 min (disabled) |
| Phone Number | +1-281-767-9141 | +1-281-626-0873 |

---

## Integration Architecture

### Webhook Flow

Both agents share the same webhook endpoint for SMS delivery status:
```
https://chatterchetah-900139201687.us-central1.run.app/api/v1/telnyx
```

### send_registration_link Tool Flow

```
1. Telnyx sends to backend:
   ├── Header: x-telnyx-call-control-id    (identifies active call)
   ├── Header: x-telnyx-from               (caller's phone, sometimes)
   └── Body: {location, level}             (extracted by AI from conversation)

2. Backend processes:
   ├── Looks up Call record by call_control_id
   ├── Retrieves caller phone from DB
   ├── Retrieves tenant_id from DB
   └── Generates registration link

3. Registration Link Format:
   https://britishswimschool.com/cypress-spring/register/?loc=[LOCATION_CODE]&type=[TYPE]

4. Backend sends SMS:
   ├── To: caller's confirmed phone number
   ├── Message: Registration link (plain text)
   └── From: Agent's assigned Telnyx number
```

### Integration Checklist

- [ ] Implement webhook receiver at `/api/v1/telnyx`
- [ ] Parse `x-telnyx-call-control-id` header from requests
- [ ] Lookup Call record in database by call_control_id
- [ ] Validate caller phone number
- [ ] Validate location code (24Spring | LALANG | LAFCypress)
- [ ] Validate level code (use URL-encoded versions for multi-word levels)
- [ ] Generate registration URL with correct parameters
- [ ] Send SMS via Telnyx to confirmed caller number
- [ ] Log transaction with call_id, location, level, timestamp
- [ ] Handle missing/invalid call records gracefully
- [ ] Implement retry logic for failed SMS sends

---

## Location Mapping

### 24 Hour Fitness Spring Energy (24Spring)
- **Address**: 1000 Lake Plaza Drive, Spring, Texas 77389
- **Primary ZIP**: 77389
- **Closest**: 77388, 77379, 77373
- **Nearby**: 77380, 77381, 77382, 77386, 77387, 77375, 77377
- **Edge**: 77070, 77069, 77068, 77090, 77073

### LA Fitness Langham Creek (LALANG)
- **Address**: 17800 Farm to Market Road 529, Houston, Texas 77095
- **Primary ZIP**: 77095
- **Closest**: 77084, 77065, 77064, 77070
- **Nearby**: 77041, 77040, 77043, 77042, 77080, 77086, 77092
- **Edge**: 77429, 77433, 77449

### LA Fitness Cypress (LAFCypress)
- **Address**: 12304 Barker Cypress Road, Cypress, Texas 77429
- **Primary ZIP**: 77429
- **Closest**: 77433, 77095
- **Nearby**: 77084, 77065, 77070, 77377, 77375
- **Edge**: 77449, 77450, 77493

---

## Pricing Reference

### First Swimmer
- One class/week: $35/class ($140/4-week month)
- Additional weekly classes: $31.50/class
- Twice per week total: $266/4-week month (8 classes)

### Additional Swimmer (Sibling)
- One class/week: $31.50/class
- Additional weekly classes: $28.35/class

### Registration Fee
- Single swimmer: $60
- Family max: $90 (one-time)

### Billing
- Monthly automatic billing on the 20th
- First month prorated if mid-month start
- Five-week months include +1 lesson/week

---

## Approved Lesson Levels

| Level | URL Encoding |
|-------|--------------|
| Tadpole | Tadpole |
| Swimboree | Swimboree |
| Seahorse | Seahorse |
| Starfish | Starfish |
| Minnow | Minnow |
| Turtle 1 | Turtle%201 |
| Turtle 2 | Turtle%202 |
| Shark 1 | Shark%201 |
| Shark 2 | Shark%202 |
| Young Adult 1 | Young%20Adult%201 |
| Young Adult 2 | Young%20Adult%202 |
| Young Adult 3 | Young%20Adult%203 |
| Adult Level 1 | Adult%20Level%201 |
| Adult Level 2 | Adult%20Level%202 |
| Adult Level 3 | Adult%20Level%203 |
| Dolphin | Dolphin |
| Barracuda | Barracuda |

---

## Phone Numbers

| Purpose | Number | Agent |
|---------|--------|-------|
| English inbound calls | +1-281-626-0873 | ChatterCheetah Voice BSS |
| Spanish inbound calls | +1-281-767-9141 | ChatterCheetah Voice BSS SP |
| Staff transfer (escalation) | +1-281-601-4588 | Both agents |

---

## Deployment Notes

1. Both agents share the same webhook endpoint for SMS delivery
2. Both agents use the same Outbound Voice Profile ID (`2859607228711699732`)
3. Agent EN must receive English calls first - it routes Spanish callers to Agent SP
4. Registration links are sent from the agent's assigned Telnyx number
5. Call transfer logic uses Handoff (EN→SP) or Transfer (to staff)
6. Conversation inactivity timeout is disabled on EN, not configured on SP
7. Data Retention: Enabled on both agents (conversation history stored)

---

## Related Documentation

- [Telnyx Webhook Setup](./TELNYX_WEBHOOK_SETUP.md) - Webhook URLs and configuration
- [Voice Prompt Implementation](./VOICE_PROMPT_IMPLEMENTATION.md) - Prompt handling details

---

## Changelog

- **2026-01-26**: Added comprehensive integration architecture, pricing, location mappings
- **2026-01-26**: Added full Spanish agent (ChatterCheetah Voice BSS SP) configuration
- **2026-01-26**: Initial documentation created
