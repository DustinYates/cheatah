# Customer Service Agent Setup Guide

This document covers the setup and configuration of the Customer Service Agent feature, which handles existing customers via SMS and phone calls using Jackrabbit CRM data through Zapier.

## Overview

The Customer Service Agent:
- Identifies existing customers by looking up their phone number in Jackrabbit via Zapier
- Routes all queries through Jackrabbit first, with LLM fallback for generic questions
- Supports both SMS and Voice channels
- Uses async webhooks for Zapier integration (outbound request + callback)

## Step 1: Run Database Migration

Connect to your database and run the migration:

```bash
# Via Cloud SQL proxy
DATABASE_URL="postgresql://postgres:<password>@127.0.0.1:5434/chattercheatah" \
  .venv/bin/alembic upgrade head

# Or directly on Cloud Run
gcloud run jobs execute alembic-migrate --region=us-central1
```

This creates three new tables:
- `tenant_customer_service_configs` - Tenant configuration
- `zapier_requests` - Request/response correlation tracking
- `jackrabbit_customers` - Cached customer data

## Step 2: Configure Zapier

### 2.1 Create Customer Lookup Zap

1. **Trigger**: Webhooks by Zapier → Catch Hook
2. **Action 1**: Jackrabbit → Find Customer by Phone
   - Map `phone_number` from the webhook payload
3. **Action 2**: Webhooks by Zapier → POST
   - URL: `{{callback_url}}` from the trigger payload
   - Payload type: JSON
   - Body:
   ```json
   {
     "correlation_id": "{{correlation_id}}",
     "type": "customer_lookup",
     "status": "success",
     "data": {
       "found": true,
       "jackrabbit_id": "{{jackrabbit_customer_id}}",
       "name": "{{customer_name}}",
       "email": "{{customer_email}}",
       "phone": "{{customer_phone}}",
       "customer_data": {
         "balance": "{{balance}}",
         "membership_type": "{{membership}}",
         "classes": "{{enrolled_classes}}"
       }
     }
   }
   ```

### 2.2 Create Customer Query Zap

1. **Trigger**: Webhooks by Zapier → Catch Hook
2. **Action 1**: Use Jackrabbit APIs or custom logic to answer the query
3. **Action 2**: Webhooks by Zapier → POST callback
   - Body:
   ```json
   {
     "correlation_id": "{{correlation_id}}",
     "type": "customer_query",
     "status": "success",
     "data": {
       "has_answer": true,
       "answer": "Your current balance is $150. Your next class is Tuesday at 4pm."
     }
   }
   ```

### 2.3 Copy Webhook URLs

After creating the Zaps, copy the webhook URLs. They look like:
```
https://hooks.zapier.com/hooks/catch/123456/abcdef/
```

## Step 3: Configure Tenant

Use the admin API to configure customer service for each tenant:

```bash
# Create/update customer service configuration
curl -X PUT "https://chattercheatah-900139201687.us-central1.run.app/api/v1/admin/customer-service/config" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "is_enabled": true,
    "zapier_webhook_url": "https://hooks.zapier.com/hooks/catch/123456/abcdef/",
    "zapier_callback_secret": "your-secret-for-hmac-verification",
    "customer_lookup_timeout_seconds": 30,
    "query_timeout_seconds": 45,
    "llm_fallback_enabled": true,
    "routing_rules": {
      "enable_sms": true,
      "enable_voice": true,
      "fallback_to_lead_capture": true,
      "auto_respond_pending_lookup": true
    }
  }'
```

### Configuration Options

| Field | Description | Default |
|-------|-------------|---------|
| `is_enabled` | Enable customer service for this tenant | `false` |
| `zapier_webhook_url` | URL for outbound webhooks to Zapier | Required |
| `zapier_callback_secret` | HMAC secret for callback verification | Optional |
| `customer_lookup_timeout_seconds` | Max wait time for customer lookup | 30 |
| `query_timeout_seconds` | Max wait time for query response | 45 |
| `llm_fallback_enabled` | Use LLM when Jackrabbit has no answer | `true` |
| `routing_rules.enable_sms` | Enable SMS channel | `true` |
| `routing_rules.enable_voice` | Enable Voice channel | `true` |
| `routing_rules.fallback_to_lead_capture` | Route unknown callers to lead capture | `true` |

## Step 4: Configure Twilio Webhooks

Point your customer service phone numbers to the new webhooks:

### For SMS
```
POST https://chattercheatah-900139201687.us-central1.run.app/api/v1/customer-service/sms/inbound
```

### For Voice
```
POST https://chattercheatah-900139201687.us-central1.run.app/api/v1/customer-service/voice/inbound
```

You can configure these in the Twilio Console or via API.

## Step 5: Test the Integration

### Test Zapier Connection

```bash
curl -X POST "https://chattercheatah-900139201687.us-central1.run.app/api/v1/admin/customer-service/test-zapier" \
  -H "Authorization: Bearer <token>"
```

### View Lookup Statistics

```bash
curl "https://chattercheatah-900139201687.us-central1.run.app/api/v1/admin/customer-service/lookup-stats?days=7" \
  -H "Authorization: Bearer <token>"
```

## API Endpoints

### Public Webhooks (no auth)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/customer-service/sms/inbound` | Twilio SMS webhook |
| `POST /api/v1/customer-service/voice/inbound` | Twilio Voice webhook |
| `POST /api/v1/customer-service/voice/gather` | Voice speech input |
| `POST /api/v1/zapier/callback` | Zapier response callback |
| `POST /api/v1/zapier/customer-update` | Cache invalidation |

### Admin Endpoints (auth required)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/admin/customer-service/config` | Get tenant config |
| `PUT /api/v1/admin/customer-service/config` | Update tenant config |
| `POST /api/v1/admin/customer-service/test-zapier` | Test Zapier connection |
| `GET /api/v1/admin/customer-service/lookup-stats` | View statistics |

## Flow Diagram

```
1. Customer texts/calls → Twilio webhook
                              ↓
2. Check if customer service enabled
                              ↓
3. Send lookup request to Zapier
   POST {zapier_webhook_url}
   {
     "type": "customer_lookup",
     "correlation_id": "uuid",
     "phone_number": "+15551234567",
     "callback_url": "https://api/v1/zapier/callback"
   }
                              ↓
4. Zapier queries Jackrabbit
                              ↓
5. Zapier calls back with customer data
   POST /api/v1/zapier/callback
                              ↓
6. If customer found → CustomerServiceAgent
   If not found → Lead capture flow
                              ↓
7. Agent queries Jackrabbit for specific questions
   or uses LLM for generic questions
                              ↓
8. Response sent to customer
```

## Troubleshooting

### Customer not being recognized

1. Check if the phone number format matches between Twilio and Jackrabbit
2. Verify the Zapier webhook is configured correctly
3. Check `zapier_requests` table for failed lookups:
   ```sql
   SELECT * FROM zapier_requests
   WHERE tenant_id = X AND status != 'completed'
   ORDER BY created_at DESC LIMIT 10;
   ```

### Slow response times

1. Check `lookup-stats` endpoint for average lookup times
2. Increase `customer_lookup_timeout_seconds` if needed
3. Consider enabling Redis caching (customers are cached for 1 hour by default)

### Callback not received

1. Verify the callback URL is accessible from Zapier
2. Check if `zapier_callback_secret` matches between config and Zap
3. Look for timeout errors in the logs

## Security Notes

- The `zapier_callback_secret` is used for HMAC-SHA256 signature verification
- Store secrets securely (don't commit to git)
- Use HTTPS for all webhook URLs
- Consider IP whitelisting for Zapier callbacks
