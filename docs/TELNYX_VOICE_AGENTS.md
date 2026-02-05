# Telnyx Voice AI Agents Configuration

This document describes the Telnyx Voice AI agent configured for British Swim School (Tenant 3).

## Overview

| Agent | Assistant ID | Phone | Purpose |
|-------|--------------|-------|---------|
| **BSS_003** | `assistant-109f3350-874f-4770-87d4-737450280441` | +1-281-767-9141 | Primary voice assistant for BSS Cypress-Spring (Tenant 3) |

### Performance Metrics
- **Model**: google/gemini-2.5-flash
- **API Key**: gemvoice

---

## Agent: BSS_03

### Basic Info

- **Name**: BSS_003
- **Assistant ID**: `assistant-109f3350-874f-4770-87d4-737450280441`
- **Phone Number**: +1-281-767-9141
- **Tenant**: BSS Cypress-Spring (Tenant 3)

### Tools Configured

1. **send_registration_link** - Webhook to send SMS registration links
2. **Send Message** - Send text messages to caller
3. **Hang Up** - End call when complete
4. **Transfer** - Transfer to staff at +1-281-601-4588

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

### Widget Configuration

```html
<telnyx-ai-agent agent-id="assistant-109f3350-874f-4770-87d4-737450280441"></telnyx-ai-agent>
<script async src="https://unpkg.com/@telnyx/ai-agent-widget@next"></script>
```

---

## Integration Architecture

### Webhook Flow

Webhook endpoint for SMS delivery status:
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
| Inbound calls | +1-281-699-0999 | BSS_03 |
| Staff transfer (escalation) | +1-281-601-4588 | BSS_03 |

---

## Deployment Notes

1. Registration links are sent from the agent's assigned Telnyx number
2. Call transfer logic uses Transfer (to staff)
3. Data Retention: Enabled (conversation history stored)

---

## Related Documentation

- [Telnyx Webhook Setup](./TELNYX_WEBHOOK_SETUP.md) - Webhook URLs and configuration
- [Voice Prompt Implementation](./VOICE_PROMPT_IMPLEMENTATION.md) - Prompt handling details

---

## Changelog

- **2026-02-05**: Updated to BSS_003 agent (assistant-109f3350-874f-4770-87d4-737450280441) on +1-281-767-9141
- **2026-01-31**: Replaced EN/SP dual-agent setup with single BSS_03 agent (assistant-9364a1b8-04ba-4cfa-b77d-c24b1fb011af)
- **2026-01-26**: Added comprehensive integration architecture, pricing, location mappings
- **2026-01-26**: Added full Spanish agent (ChatterCheetah Voice BSS SP) configuration
- **2026-01-26**: Initial documentation created
