# Voice Prompt Implementation Guide

## Overview

This document describes how to automatically convert text/chat prompts into voice-safe prompts for Telnyx AI Assistant, and all the credentials/infrastructure required for production deployment.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INBOUND CALL FLOW                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Caller dials tenant phone number (e.g., +12817679141)          │
│                           │                                         │
│                           ▼                                         │
│  2. Telnyx AI Assistant receives call                              │
│                           │                                         │
│                           ▼                                         │
│  3. Telnyx calls Dynamic Variables Webhook:                        │
│     POST https://chattercheatah-xxx.run.app/api/v1/telnyx/dynamic-variables
│     Body: { "to": "+12817679141", "from": "+1234567890" }          │
│                           │                                         │
│                           ▼                                         │
│  4. Our API:                                                        │
│     a) Looks up tenant by phone number                             │
│     b) Fetches tenant's chat prompt (PromptBundle)                 │
│     c) CONVERTS chat prompt → voice prompt (NEW)                   │
│     d) Returns: { "X": "<voice-safe system prompt>" }              │
│                           │                                         │
│                           ▼                                         │
│  5. Telnyx AI Assistant uses prompt to converse with caller        │
│                           │                                         │
│                           ▼                                         │
│  6. Call ends → Telnyx sends insights webhook                      │
│     POST /api/v1/telnyx/ai-call-complete                           │
│                           │                                         │
│                           ▼                                         │
│  7. Lead created/updated on Dashboard                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Current State

### Existing Endpoint
- **File**: `app/api/routes/telnyx_webhooks.py` (lines 42-117)
- **Endpoint**: `POST /api/v1/telnyx/dynamic-variables`
- **Current behavior**: Calls `prompt_service.compose_prompt_voice(tenant_id)` which returns the RAW chat prompt

### What Needs to Change
- Create a voice prompt transformer that converts chat prompts to voice-safe prompts
- The transformer applies the universal voice constraints (no URLs, one question at a time, etc.)
- This happens in real-time when Telnyx requests the dynamic variable

---

## Implementation Plan

### Step 1: Create Voice Prompt Transformer Service

Create a new service that transforms any text prompt into a voice-safe prompt:

**File**: `app/domain/services/voice_prompt_transformer.py`

```python
"""Voice Prompt Transformer - Converts chat prompts to voice-safe prompts."""

import re
from typing import Optional

# Voice meta-prompt that wraps any business prompt
VOICE_META_PROMPT = '''You are a voice assistant. You communicate through spoken conversation only.

## CRITICAL VOICE RULES (NEVER VIOLATE)

### Speech Safety
- NEVER read URLs, email addresses, or web links aloud
- NEVER speak special characters or symbols (@, #, /, etc.)
- NEVER read codes, IDs, tokens, or formatted text
- Replace visual references with spoken explanations
- NEVER assume the caller can see anything

### Response Structure
- Keep responses SHORT (2-3 sentences max)
- Ask only ONE question per turn
- Avoid lists longer than 3 items unless asked
- End naturally to allow interruption
- Break complex info into multiple turns

### Conversational Flow
- Use confirmation checkpoints: "Does that make sense?" / "Would you like more detail?"
- Restate critical info simply
- Avoid jargon unless caller uses it first
- Use listening cues: "Got it." / "Okay." / "That helps."

### Delivery Style
- Speak numbers slowly and clearly
- Avoid abbreviations (say "appointment" not "appt")
- No parentheticals or asides
- Use plain, natural language
- Sound warm and helpful, not robotic

### Information Handling
- For links/websites: "I can text or email that to you. Which works better?"
- For addresses: Give location name first, full address only if asked
- For lists: Summarize first, offer to go item-by-item
- For policies: Explain what it means and what they need to do
- For data collection: Ask for ONE piece of info at a time

---

## YOUR BUSINESS CONTEXT

{business_prompt}

---

## REMEMBER
You are on a PHONE CALL. The person cannot see anything. Keep it conversational, brief, and helpful.
'''


def transform_chat_to_voice(chat_prompt: str) -> str:
    """Transform a chat/text prompt into a voice-safe prompt.

    Args:
        chat_prompt: The original text-based chatbot prompt

    Returns:
        A voice-safe version of the prompt wrapped in voice constraints
    """
    if not chat_prompt:
        return VOICE_META_PROMPT.format(business_prompt="Help the caller with their questions.")

    # Clean the chat prompt for voice use
    cleaned_prompt = _clean_for_voice(chat_prompt)

    # Wrap in voice meta-prompt
    return VOICE_META_PROMPT.format(business_prompt=cleaned_prompt)


def _clean_for_voice(text: str) -> str:
    """Clean text content for voice delivery.

    Removes or transforms elements that don't work well in spoken format.
    """
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
    text = re.sub(r'`(.+?)`', r'\1', text)        # Code
    text = re.sub(r'#{1,6}\s*', '', text)         # Headers

    # Remove URLs but keep context
    text = re.sub(
        r'https?://[^\s\)]+',
        '[website link - offer to send via text/email]',
        text
    )

    # Remove email addresses but keep context
    text = re.sub(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        '[email address - offer to send via text]',
        text
    )

    # Convert bullet points to spoken format
    text = re.sub(r'^[\s]*[-•*]\s*', 'Option: ', text, flags=re.MULTILINE)

    # Convert numbered lists to spoken format
    text = re.sub(r'^[\s]*\d+\.\s*', 'Next: ', text, flags=re.MULTILINE)

    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()
```

### Step 2: Update the Dynamic Variables Endpoint

Modify the existing endpoint to use the transformer:

**File**: `app/api/routes/telnyx_webhooks.py`

```python
# Add import at top
from app.domain.services.voice_prompt_transformer import transform_chat_to_voice

# In the dynamic_variables endpoint (around line 100), change:
# FROM:
system_prompt = await prompt_service.compose_prompt_voice(tenant_id)

# TO:
chat_prompt = await prompt_service.compose_prompt_voice(tenant_id)
system_prompt = transform_chat_to_voice(chat_prompt)
```

### Step 3: Update PromptService (if needed)

The existing `compose_prompt_voice()` method should return the raw business prompt.
The transformation happens after.

**File**: `app/domain/services/prompt_service.py`

Ensure `compose_prompt_voice()` returns the business-specific content without voice formatting.

---

## Credentials & Infrastructure Required

### 1. Telnyx Credentials

| Credential | Location | Purpose |
|------------|----------|---------|
| `TELNYX_API_KEY` | Cloud Run env var | API authentication |
| `TELNYX_PUBLIC_KEY` | Cloud Run env var | Webhook signature verification |
| Connection ID | Per-tenant in DB | Links phone number to TeXML app |

**Where to find:**
- Telnyx Portal → API Keys → Create new V2 API Key
- Telnyx Portal → AI → AI Assistants → Your Assistant → Settings

**Current values (production):**
```
TELNYX_API_KEY=<stored in Cloud Run env vars - see GCP Console>
```

### 2. Google Cloud Platform (GCP) Credentials

| Credential | Purpose |
|------------|---------|
| `GOOGLE_CLOUD_PROJECT` | Project ID for Cloud Run |
| Service Account JSON | Authentication for Cloud Tasks, etc. |
| Cloud Run Service URL | Base URL for webhooks |

**Production values:**
```
Project: chattercheetah (or similar)
Region: us-central1
Service URL: https://chattercheatah-900139201687.us-central1.run.app
```

**How to deploy:**
```bash
gcloud run deploy chattercheatah \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "TELNYX_API_KEY=xxx,DATABASE_URL=xxx"
```

### 3. Supabase (PostgreSQL) Credentials

| Credential | Purpose |
|------------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SUPABASE_URL` | Supabase project URL (if using client) |
| `SUPABASE_KEY` | Supabase anon/service key |

**Format:**
```
DATABASE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
```

**Where to find:**
- Supabase Dashboard → Project Settings → Database → Connection string
- Use "Transaction pooler" (port 6543) for serverless

### 4. Environment Variables Summary

Create/update in Cloud Run:

```bash
# Telnyx
TELNYX_API_KEY=<your-telnyx-api-key>
TELNYX_PUBLIC_KEY=<from telnyx portal>

# Database
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[pass]@aws-0-us-west-1.pooler.supabase.com:6543/postgres

# GCP
GOOGLE_CLOUD_PROJECT=<your-project-id>

# App
ENVIRONMENT=production
LOG_LEVEL=INFO
```

---

## Telnyx AI Assistant Configuration

### In Telnyx Portal:

1. **Create AI Assistant**
   - Navigate to: AI → AI Assistants → Create
   - Name: "ChatterCheetah Voice Assistant"

2. **Configure Dynamic Variables**
   - Webhook URL: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/dynamic-variables`
   - HTTP Method: POST
   - Variable Name: `X` (this becomes the system prompt)

3. **Configure Insight Groups** (for post-call data)
   - Enable "Post-call Insights"
   - Webhook URL: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/ai-call-complete`

4. **Assign Phone Numbers**
   - Go to Numbers → My Numbers
   - Select each tenant's number
   - Assign to this AI Assistant

---

## Database Tables Involved

### TenantSmsConfig
```sql
-- Check voice is enabled
SELECT tenant_id, telnyx_phone_number, voice_enabled, telnyx_connection_id
FROM tenant_sms_configs;
```

### TenantVoiceConfig
```sql
-- Voice-specific settings
SELECT tenant_id, is_enabled, handoff_mode, default_greeting
FROM tenant_voice_configs;
```

### PromptBundles
```sql
-- The chat prompts that get transformed to voice
SELECT tenant_id, system_prompt, lead_capture_fields
FROM prompt_bundles;
```

---

## Testing the Implementation

### 1. Test Dynamic Variables Endpoint
```bash
curl -X POST https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/dynamic-variables \
  -H "Content-Type: application/json" \
  -d '{"to": "+12817679141", "from": "+1234567890", "direction": "inbound"}'
```

Expected response:
```json
{
  "X": "You are a voice assistant. You communicate through spoken conversation only.\n\n## CRITICAL VOICE RULES...\n\n## YOUR BUSINESS CONTEXT\n[transformed business prompt]\n..."
}
```

### 2. Test Live Call
1. Call the tenant's phone number
2. Verify AI answers appropriately
3. Check that it follows voice rules (no URLs spoken, short responses, etc.)

### 3. Verify Lead Creation
After the call:
1. Check Dashboard for new lead with phone icon
2. Verify call summary appears in lead details

---

## Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `app/domain/services/voice_prompt_transformer.py` | CREATE | Voice prompt transformation logic |
| `app/api/routes/telnyx_webhooks.py` | MODIFY | Use transformer in dynamic-variables endpoint |
| `app/domain/services/prompt_service.py` | VERIFY | Ensure compose_prompt_voice returns raw prompt |

---

## Voice Prompt Transformation Rules Summary

### Always Remove/Transform:
- URLs → "I can send that link via text"
- Email addresses → "I can text you that email"
- Markdown formatting → Plain text
- Long lists → Summarize + offer details
- Special characters → Spell out or remove

### Always Add:
- Confirmation checkpoints
- One question per turn limit
- Short response requirement
- Interruption-friendly endings

### Tone Requirements:
- Warm, helpful
- Not robotic
- Clear and slow for important info
- Natural conversation flow

---

## Quick Start for New Session

Copy this to start a new Claude Code session:

```
I need to implement voice prompt transformation for ChatterCheetah.

Current state:
- Telnyx AI Assistant calls /api/v1/telnyx/dynamic-variables to get system prompt
- Currently returns raw chat prompt from PromptBundle
- Need to transform chat prompt → voice-safe prompt

Tasks:
1. Create app/domain/services/voice_prompt_transformer.py
   - transform_chat_to_voice(chat_prompt) function
   - Wraps business prompt in voice constraints
   - Removes URLs, markdown, long lists

2. Update app/api/routes/telnyx_webhooks.py
   - Import and use transformer in dynamic_variables endpoint
   - Line ~100: transform the prompt before returning

3. Deploy to Cloud Run and test

Production environment:
- Cloud Run: chattercheatah-900139201687.us-central1.run.app
- Database: Supabase PostgreSQL
- Telnyx API Key: Already configured in env vars

Reference the voice transformation rules in this file.
```
