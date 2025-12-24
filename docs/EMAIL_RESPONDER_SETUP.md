# Email Responder Setup Guide

This guide covers the setup and configuration of the Gmail-based email responder for Chatter Cheetah.

## Overview

The email responder allows tenants to connect their Gmail/Google Workspace accounts and automatically respond to customer emails with AI-powered responses. It uses:

- **Gmail API** for reading and sending emails
- **Google Cloud Pub/Sub** for real-time push notifications
- **OAuth 2.0** for secure tenant authentication

## Architecture

```
Inbound Email → Gmail → Pub/Sub Push → Webhook → Cloud Tasks → Email Worker → LLM → Gmail Reply
```

## GCP Setup

### 1. Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** → **Credentials**
3. Click **Create Credentials** → **OAuth client ID**
4. Select **Web application**
5. Configure:
   - **Name**: `Chatter Cheetah Email`
   - **Authorized redirect URIs**: 
     - `https://your-domain.com/api/v1/email/oauth/callback`
     - `http://localhost:8000/api/v1/email/oauth/callback` (for development)
6. Save the **Client ID** and **Client Secret**

### 2. Enable Gmail API

1. Go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click **Enable**

### 3. Create Pub/Sub Topic

1. Go to **Pub/Sub** → **Topics**
2. Click **Create Topic**
3. Name it: `gmail-push-notifications`
4. Click **Create**

### 4. Grant Gmail API Permission to Pub/Sub (CRITICAL)

**This step is required for Gmail watch to work.** Without it, you'll get a 403 Forbidden error when setting up push notifications.

**Option A: Via gcloud CLI (Recommended)**

```bash
gcloud pubsub topics add-iam-policy-binding gmail-push-notifications \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=chatbots-466618
```

**Option B: Via Google Cloud Console**

1. Go to **IAM & Admin** → **IAM**
2. Click **Grant Access**
3. Add principal: `gmail-api-push@system.gserviceaccount.com`
4. Assign role: **Pub/Sub Publisher**
5. Click **Save**

### 5. Create Pub/Sub Subscription

1. Go to **Pub/Sub** → **Subscriptions**
2. Click **Create Subscription**
3. Configure:
   - **Subscription ID**: `gmail-push-subscription`
   - **Topic**: `gmail-push-notifications`
   - **Delivery type**: Push
   - **Endpoint URL**: `https://your-domain.com/api/v1/email/pubsub`
4. Click **Create**

## Environment Variables

Add these to your `.env` file or GCP Secret Manager:

```bash
# Gmail OAuth
GMAIL_CLIENT_ID=your-oauth-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-oauth-client-secret
GMAIL_PUBSUB_TOPIC=projects/your-project/topics/gmail-push-notifications
GMAIL_OAUTH_REDIRECT_URI=https://your-domain.com/api/v1/email/oauth/callback

# Email Worker (Cloud Tasks)
CLOUD_TASKS_EMAIL_WORKER_URL=https://your-domain.com/workers/email
```

## Cloud Run Configuration

Update your Cloud Run service with the new environment variables:

```bash
gcloud run services update chattercheatah \
  --region us-central1 \
  --update-env-vars="GMAIL_CLIENT_ID=xxx" \
  --update-env-vars="GMAIL_CLIENT_SECRET=xxx" \
  --update-env-vars="GMAIL_PUBSUB_TOPIC=projects/xxx/topics/gmail-push-notifications" \
  --update-env-vars="GMAIL_OAUTH_REDIRECT_URI=https://xxx/api/v1/email/oauth/callback" \
  --update-env-vars="CLOUD_TASKS_EMAIL_WORKER_URL=https://xxx/workers/email"
```

## Database Migration

Run the migration to create email tables:

```bash
uv run alembic upgrade head
```

## User Flow

1. Tenant navigates to **Email Settings** in the dashboard
2. Clicks **Connect Gmail**
3. Redirected to Google OAuth consent screen
4. Grants permissions to read/send emails
5. Redirected back with success message
6. Email responder is now active

## Gmail Watch Refresh

Gmail push notification watches expire after 7 days. The system includes:

- Manual refresh button in Email Settings
- Worker endpoint for scheduled refresh: `POST /workers/email/refresh-gmail-watch`

Set up Cloud Scheduler to call the refresh endpoint daily:

```bash
gcloud scheduler jobs create http gmail-watch-refresh \
  --location us-central1 \
  --schedule "0 6 * * *" \
  --uri "https://your-domain.com/workers/email/refresh-gmail-watch" \
  --http-method POST \
  --oidc-service-account-email your-service-account@project.iam.gserviceaccount.com
```

## Features

### Business Hours
- Configure business hours in Email Settings
- Auto-reply outside hours with customizable message

### Escalation
- Keyword-based escalation (urgent, complaint, etc.)
- Human handoff detection from email content

### Lead Capture
- Automatic extraction of contact info from emails
- Links email conversations to existing contacts/leads

### Thread Context
- Uses email thread history for LLM context
- Configurable thread depth (default: 10 messages)

## Testing

### Local Development

1. Use ngrok to expose local endpoint:
   ```bash
   ngrok http 8000
   ```

2. Update OAuth redirect URI and Pub/Sub subscription with ngrok URL

3. Connect a test Gmail account

### Test Endpoint

Use the test endpoint (development only):

```bash
curl -X POST http://localhost:8000/api/v1/email/pubsub/test \
  -H "Content-Type: application/json" \
  -d '{"email_address": "test@example.com", "history_id": "12345"}'
```

## Troubleshooting

### OAuth Errors

- **redirect_uri_mismatch**: Check that the redirect URI exactly matches the one in Google Cloud Console
- **access_denied**: User denied permissions or Gmail API not enabled

### Gmail Watch 403 Forbidden Error

**Error message:**
```
Failed to setup watch: <HttpError 403 ... "Error sending test message to Cloud PubSub ... 
User not authorized to perform this action."
```

**Cause:** The Gmail API service account doesn't have permission to publish to the Pub/Sub topic.

**Solution:**
```bash
gcloud pubsub topics add-iam-policy-binding gmail-push-notifications \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=chatbots-466618
```

### Gmail Watch 404 Not Found Error

**Cause:** The Pub/Sub topic doesn't exist.

**Solution:**
```bash
gcloud pubsub topics create gmail-push-notifications \
  --project=chatbots-466618
```

Then grant permissions as described above.

### Push Notifications Not Working

1. Verify Pub/Sub topic exists: `gcloud pubsub topics describe gmail-push-notifications --project=chatbots-466618`
2. Check that `gmail-api-push@system.gserviceaccount.com` has Publisher role on the topic
3. Verify subscription endpoint is accessible
4. Check webhook logs for errors
5. Click "Refresh Watch" in Email Settings to re-establish the watch

### Token Refresh Failures

- Refresh tokens may be revoked if user removes app access
- Tenant needs to reconnect Gmail if tokens become invalid

## Security Considerations

- OAuth tokens are stored in the database (consider encryption)
- Pub/Sub authentication token verification can be enabled in production
- All email content processed in memory, not stored long-term
- Audit trail via message metadata in conversations table

