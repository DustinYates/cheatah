# Telnyx Webhook Configuration Guide

## Quick Reference

### Correct Webhook URLs

| Webhook Type | URL Path | Full URL |
|-------------|----------|----------|
| **Inbound SMS** | `/api/v1/telnyx/sms/inbound` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound` |
| **SMS Status Callback** | `/api/v1/telnyx/sms/status` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status` |
| **Voice AI (Dynamic Variables)** | `/api/v1/telnyx/dynamic-variables` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/dynamic-variables` |
| **Voice AI (Call Complete)** | `/api/v1/telnyx/ai-call-complete` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/ai-call-complete` |
| **Voice AI Tool (Registration Link)** | `/api/v1/telnyx/tools/send-registration-link` | `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/tools/send-registration-link` |

## Common Mistakes

### ❌ WRONG - Will cause 405 errors
```
/api/v1/sms/telnyx/status  ← "sms" and "telnyx" are swapped!
/api/v1/sms/telnyx/inbound
```

### ✅ CORRECT
```
/api/v1/telnyx/sms/status  ← "telnyx" comes before "sms"
/api/v1/telnyx/sms/inbound
```

## Configuration Steps

### 1. Configure Messaging Profile (for SMS)

1. Go to [Telnyx Portal](https://portal.telnyx.com) → **Messaging** → **Messaging Profiles**
2. Select your messaging profile (or create a new one)

#### Inbound Tab
- **Webhook URL**: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/inbound`
- **HTTP Method**: POST
- **Failover URL**: (optional) Can use alternate path: `/api/v1/telnyx/inbound`

#### Outbound Tab
- **Send webhooks**: Enable
- **Webhook URL**: `https://chattercheatah-900139201687.us-central1.run.app/api/v1/telnyx/sms/status`
- **Webhook event types**: Select all (message.sent, message.delivered, message.failed, message.finalized)

### 2. Verify Configuration

After saving, send a test SMS:

```bash
# Test inbound SMS
# Text any message to your Telnyx number and check Cloud Run logs:
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'Telnyx SMS webhook received'" --limit 5 --project chatbots-466618

# Test outbound SMS status
# Check for status update webhooks:
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'Telnyx status update'" --limit 5 --project chatbots-466618
```

### 3. Troubleshooting

#### SMS sends but shows "Failed" in Telnyx portal

**Symptoms:**
- Messages are delivered to recipient
- Telnyx portal shows all messages as "Failed"
- Delivery logs show error code 405

**Cause:** Status callback webhook URL is incorrect

**Solution:**
1. Check the webhook URL in your messaging profile
2. Verify it's `/api/v1/telnyx/sms/status` NOT `/api/v1/sms/telnyx/status`
3. Save and test again

#### Inbound SMS not received

**Symptoms:**
- User texts the number
- No response from bot
- No logs in Cloud Run

**Cause:** Inbound webhook URL is incorrect or messaging profile not assigned

**Solution:**
1. Verify webhook URL: `/api/v1/telnyx/sms/inbound`
2. Check phone number is assigned to correct messaging profile
3. Check 10DLC campaign is active

## Route Structure

The FastAPI application routes are structured as follows:

```
app.py
├─ /api/v1 (API prefix)
   └─ /telnyx (router prefix from telnyx_webhooks.py)
      ├─ /sms/inbound (endpoint)
      ├─ /sms/status (endpoint)
      ├─ /inbound (alternate endpoint, backwards compat)
      ├─ /dynamic-variables (voice AI endpoint)
      └─ /ai-call-complete (voice AI endpoint)
```

**Full paths:**
- `/api/v1/telnyx/sms/inbound`
- `/api/v1/telnyx/sms/status`

## Code Reference

The webhook handlers are defined in:
- File: [`app/api/routes/telnyx_webhooks.py`](../app/api/routes/telnyx_webhooks.py)
- Inbound SMS handler: Line 261-367
- Status callback handler: Line 369-396
- Router mounted: [`app/api/routes/__init__.py`](../app/api/routes/__init__.py) Line 20

## Additional Resources

- [Telnyx Voice AI Agents](./TELNYX_VOICE_AGENTS.md) - Configuration for the two voice agents (English & Spanish)
- [Telnyx SMS API Documentation](https://developers.telnyx.com/docs/api/v2/messaging)
- [Telnyx Webhook Security](https://developers.telnyx.com/docs/v2/messaging/quickstarts/webhooks)
- [10DLC Registration Guide](https://developers.telnyx.com/docs/v2/messaging/10dlc-registration)
