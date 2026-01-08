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
- Run: `gcloud run services update chattercheatah --update-env-vars="CLOUD_TASKS_WORKER_URL=https://chattercheatah-iyv6z6wp7a-uc.a.run.app/workers"`

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

## Telnyx Webhook Configuration

If using Telnyx, configure these webhooks in Telnyx Mission Control:

- SMS Inbound: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound`
- SMS Status: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
