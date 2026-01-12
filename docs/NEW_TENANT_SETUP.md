# New Tenant Setup Checklist

This document outlines the steps required to fully configure a new tenant in ChatterCheetah.

## 1. Create Tenant in Admin Panel

1. Go to **Manage Tenants** (admin only, no tenant selected)
2. Click **Add Tenant**
3. Enter tenant name and save

## 2. Configure Business Profile

1. Switch to the new tenant using the dropdown
2. Go to **Settings > Business Profile**
3. Fill in:
   - Business Name
   - Website URL (click "Scrape Website" to auto-extract info)
   - Phone Number
   - Email Address
4. Save changes

## 3. Configure Telephony (SMS/Voice)

**This is critical for SMS follow-ups to work.**

1. Go to **Settings > Telephony**
2. Select provider (Telnyx or Twilio)
3. Enter credentials:

### For Telnyx:
- **API Key**: Get from https://portal.telnyx.com > API Keys
  - Can reuse the same API key across multiple tenants
- **Messaging Profile ID**: From Telnyx Mission Control > Messaging > Messaging Profiles
- **SMS Phone Number**: The Telnyx number assigned to this tenant (e.g., +12816260873)

### For Twilio:
- **Account SID**: From Twilio Console
- **Auth Token**: From Twilio Console
- **SMS Phone Number**: The Twilio number assigned to this tenant

4. Enable SMS toggle
5. Click "Test Credentials" to verify
6. Save Configuration

## 4. Configure Email Integration (Optional)

1. Go to **Settings > Email Setup**
2. Connect Gmail account for the tenant's intake email
3. Configure email-to-lead mapping

## 5. Configure SMS Auto Follow-up

1. Go to **Communications > SMS** (or the SMS page)
2. Enable "Auto Follow-up for New Leads"
3. Configure:
   - Delay before sending (default: 5 minutes)
   - Sources that trigger follow-up (voice_call, sms, email)

## 6. Configure Prompts

1. Go to **Settings > Prompts Setup**
2. Use the Prompt Wizard to configure the AI assistant
3. Review scraped website data for pre-filled suggestions

## Common Issues

### "Server misconfiguration: worker URL not set"
- The `CLOUD_TASKS_WORKER_URL` environment variable is missing from Cloud Run
- Run: `gcloud run services update chattercheatah --update-env-vars="CLOUD_TASKS_WORKER_URL=https://chattercheatah-900139201687.us-central1.run.app/workers/process-sms"`

### "Could not get SMS provider for tenant X"
- Telephony credentials not configured
- Go to Settings > Telephony and enter API key

### "Invalid Telnyx API key"
- API key is expired or incorrect
- Get a new API v2 key from Telnyx portal

### "Phone not opted in, skipping follow-up"
- The phone number hasn't consented to receive SMS
- Leads from voice calls auto-opt-in with implied consent
- Leads from other sources need explicit opt-in

### SMS not being sent after email intake
1. Check email is being processed (Cloud Logging)
2. Check lead is created with phone number
3. Check SMS config is enabled for tenant
4. Check auto follow-up is enabled
5. Check Telephony credentials are valid

## Environment Variables (Cloud Run)

These are set in `scripts/deploy-cloud-run.sh`:

| Variable | Description |
|----------|-------------|
| `CLOUD_TASKS_WORKER_URL` | URL for the follow-up worker endpoint |
| `TWILIO_WEBHOOK_URL_BASE` | Base URL for Twilio/Telnyx webhooks |
| `GEMINI_API_KEY` | Google AI API key (stored as secret) |
| `DATABASE_URL` | PostgreSQL connection string (stored as secret) |

## Telnyx Setup (CRITICAL for New Tenants)

### 1. 10DLC Compliance (Required for US SMS)

Before a Telnyx phone number can send/receive SMS in the US, it MUST be registered with a 10DLC campaign:

1. Go to **Telnyx Portal** → **Messaging** → **Compliance**
2. Create or use existing 10DLC Brand (company verification)
3. Create a 10DLC Campaign (describe SMS use case)
4. Assign the phone number to the campaign
5. Wait for approval (can take 24-48 hours)

**Without 10DLC registration:**
- Outbound SMS will fail with "not 10DLC-registered" error
- Inbound SMS won't be delivered by carriers

### 2. Messaging Profile Configuration

Each tenant needs a Telnyx Messaging Profile with correct webhook URLs:

1. Go to **Telnyx Portal** → **Messaging** → **Messaging Profiles**
2. Create a new profile (e.g., "Tenant Name")
3. Configure **Inbound** tab:
   - **Webhook URL**: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound`
   - ⚠️ **VERIFY THE PATH**: Should be `/telnyx/sms/` NOT `/sms/telnyx/`
4. Configure **Outbound** tab (for delivery status callbacks):
   - **Status Callback URL**: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
   - ⚠️ **CRITICAL**: Must be `/api/v1/telnyx/sms/status` (NOT `/api/v1/sms/telnyx/status`)
   - Without this, SMS will send but delivery confirmations won't be received (405 errors in Telnyx portal)
5. Assign phone number(s) to this messaging profile

### 3. Phone Number Assignment

1. Go to **Telnyx Portal** → **Numbers** → **My Numbers**
2. Click on the phone number
3. Assign to the correct Messaging Profile
4. Verify 10DLC campaign shows "Assigned" status

### Telnyx Webhook URLs

⚠️ **IMPORTANT**: The order matters! Use `/telnyx/sms/` NOT `/sms/telnyx/`

| Webhook Type | Correct URL | Common Mistake |
|-------------|-----|----------------|
| Inbound SMS | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound` | ❌ `/api/v1/sms/telnyx/inbound` |
| SMS Status Callback | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status` | ❌ `/api/v1/sms/telnyx/status` (causes 405 error) |
| Voice (TeXML) | Configure in Telnyx TeXML Application settings | N/A |

**Alternate paths (backwards compatibility):**
- `/api/v1/telnyx/inbound` also works for inbound SMS

## SMS Opt-In Behavior

- **Auto opt-in**: Users are automatically opted in when they text inbound
- **STOP keyword**: User texts "STOP" → opted out, receives unsubscribe confirmation
- **START keyword**: User texts "START" → opted back in
- **HELP keyword**: User receives help message with options
- Opt-in status is tracked per phone number per tenant in `sms_opt_ins` table

---

## Voice Setup (Telnyx AI Assistant)

Voice functionality uses Telnyx AI Assistant to handle inbound calls with tenant-specific AI responses.

### Step 1: Database Configuration

Run the voice config setup script to create `TenantVoiceConfig` record:

```bash
cd /path/to/chattercheetah
source .venv/bin/activate
python scripts/setup_voice_configs.py
```

Or create manually by adding to `TENANT_CONFIGS` in the script:
```python
{
    "tenant_id": <TENANT_ID>,
    "name": "Tenant Name",
    "greeting": "Hello! Thank you for calling [Business Name]. I'm an AI assistant here to help you. How can I assist you today?",
}
```

This creates:
- `TenantVoiceConfig` record with `is_enabled=True`
- Sets `voice_enabled=True` in `TenantSmsConfig`

### Step 2: Create Telnyx AI Assistant

1. Go to **Telnyx Portal** → **AI** → **AI Assistants**
2. Click **Create AI Assistant**
3. Name it: `[Tenant Name] Voice`
4. In the **Instructions/System Prompt** field, paste the tenant's full prompt including:
   - Business identity
   - Locations/services
   - Pricing info (if applicable)
   - Behavioral instructions
5. Save the assistant

**Example System Prompt:**
```
BUSINESS IDENTITY:
You are supporting [Business Name].

LOCATIONS:
1) [Location 1] - [Address]
2) [Location 2] - [Address]

SERVICES:
[List of services]

PRICING:
[Pricing information]

Be warm, friendly, and helpful. Answer questions about locations, services, and scheduling.
If you don't know something specific, offer to have someone call them back.
```

### Step 3: Assign Phone Number

1. Go to **AI Assistants** → Click on the assistant
2. Go to **Calling** tab → **Assigned Phone Numbers**
3. Add the tenant's phone number (e.g., +1-281-626-0873)
4. Save

### Step 4: Test Voice

1. Call the assigned phone number
2. Test questions:
   - "What locations do you have?"
   - "What services do you offer?"
   - "How much does it cost?"
3. Verify AI responds with tenant-specific information

### Voice Configuration Notes

- **One AI Assistant per tenant**: Each tenant needs their own AI Assistant with their specific prompt
- **Dynamic variables webhook** (`/api/v1/telnyx/dynamic-variables`): Available but not currently used - prompts are hardcoded in Telnyx portal for reliability
- **Ring delay**: Configure in Telnyx AI Assistant settings if you want the phone to ring before AI answers
- **Database records**: `TenantVoiceConfig` stores handoff settings, greetings, escalation rules (for future TeXML integration)

### Voice Troubleshooting

| Issue | Solution |
|-------|----------|
| AI gives generic responses | Check System Prompt in Telnyx portal contains tenant-specific info |
| Calls not connecting | Verify phone number is assigned to AI Assistant |
| No voice at all | Check phone number has voice enabled in Telnyx Numbers settings |
| Want to change AI personality | Edit Instructions field in Telnyx AI Assistant |
