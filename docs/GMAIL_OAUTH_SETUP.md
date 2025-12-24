# Gmail OAuth Setup Guide

This guide will help you set up Gmail OAuth credentials for the Email Responder feature.

## Prerequisites

- Gmail API enabled (already done ✅)
- Pub/Sub topic created (already done ✅)
- Access to Google Cloud Console

## Step-by-Step Setup

### Step 1: Configure OAuth Consent Screen

1. Go to [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent?project=chatbots-466618)

2. If not already configured, set up the consent screen:
   - **User Type**: Choose "External" (or "Internal" if using Google Workspace)
   - **App name**: `Chatter Cheetah`
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
   - Click "Save and Continue"
   - **Scopes**: Click "Add or Remove Scopes" and add:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.send`
     - `https://www.googleapis.com/auth/gmail.modify`
   - Click "Save and Continue"
   - **Test users**: Add any email addresses that will be testing the integration
   - Click "Save and Continue"

### Step 2: Create OAuth 2.0 Client ID

1. Go to [Credentials](https://console.cloud.google.com/apis/credentials?project=chatbots-466618)

2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**

3. Configure the OAuth client:
   - **Application type**: Web application
   - **Name**: `Chatter Cheetah Gmail Client`
   - **Authorized redirect URIs**: Add:
     ```
     https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback
     ```
   - Click **"CREATE"**

4. **Copy the Client ID and Client Secret** - you'll need these for the next step

### Step 3: Run the Setup Script

Run the automated setup script:

```bash
cd /Users/dustinyates/Desktop/chattercheetah
./scripts/setup_gmail_oauth.sh
```

The script will:
- Prompt you for the Client ID and Client Secret
- Create GCP secrets for secure storage
- Grant Cloud Run service account access to the secrets
- Update the Cloud Run service with the necessary environment variables

### Step 4: Verify Setup

1. Wait for Cloud Run to deploy the new revision (usually takes 1-2 minutes)

2. Go to the Email Settings page: https://chattercheatah-frontend-900139201687.us-central1.run.app/email

3. Click "Connect Gmail" - you should be redirected to Google's OAuth consent page

4. After authorizing, you'll be redirected back and see "Connected" status

## Manual Setup (Alternative)

If you prefer to set up manually:

### Create Secrets

```bash
# Create secret for Client ID
echo -n "YOUR_CLIENT_ID" | gcloud secrets create gmail-client-id \
    --data-file=- \
    --project=chatbots-466618

# Create secret for Client Secret
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create gmail-client-secret \
    --data-file=- \
    --project=chatbots-466618
```

### Grant Access

```bash
# Get the service account
SERVICE_ACCOUNT=$(gcloud run services describe chattercheatah \
    --region=us-central1 \
    --project=chatbots-466618 \
    --format="value(spec.template.spec.serviceAccountName)")

# Grant access to secrets
gcloud secrets add-iam-policy-binding gmail-client-id \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=chatbots-466618

gcloud secrets add-iam-policy-binding gmail-client-secret \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=chatbots-466618
```

### Update Cloud Run Service

```bash
gcloud run services update chattercheatah \
    --region=us-central1 \
    --project=chatbots-466618 \
    --update-secrets="GMAIL_CLIENT_ID=gmail-client-id:latest,GMAIL_CLIENT_SECRET=gmail-client-secret:latest" \
    --update-env-vars="GMAIL_OAUTH_REDIRECT_URI=https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback,GMAIL_PUBSUB_TOPIC=projects/chatbots-466618/topics/gmail-push-notifications"
```

## Troubleshooting

### "Gmail integration not configured" Error

- Verify secrets exist: `gcloud secrets list --project=chatbots-466618 | grep gmail`
- Check Cloud Run environment variables are set correctly
- Ensure service account has access to secrets

### OAuth Redirect URI Mismatch

- Verify the redirect URI in OAuth credentials matches exactly:
  `https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback`
- No trailing slashes or differences in protocol (http vs https)

### Consent Screen Issues

- For external apps, you may need to verify the app with Google
- Add test users in the OAuth consent screen if in testing mode
- Ensure required scopes are added to the consent screen

### Gmail Watch 403 Forbidden Error

**Error message:**
```
Failed to setup watch: <HttpError 403 when requesting https://gmail.googleapis.com/gmail/v1/users/me/watch?alt=json
returned "Error sending test message to Cloud PubSub ... User not authorized to perform this action."
```

**Cause:** The Gmail API service account (`gmail-api-push@system.gserviceaccount.com`) doesn't have permission to publish to the Pub/Sub topic. When Gmail sets up a watch, it sends a test message to verify the connection.

**Solution:** Grant the Gmail API service account the Pub/Sub Publisher role:

```bash
gcloud pubsub topics add-iam-policy-binding gmail-push-notifications \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=chatbots-466618
```

After granting permissions, click "Refresh Watch" in Email Settings.

### Gmail Watch 404 Not Found Error

**Cause:** The Pub/Sub topic doesn't exist.

**Solution:** Create the topic:

```bash
gcloud pubsub topics create gmail-push-notifications \
  --project=chatbots-466618
```

Then grant permissions as described above.

## Next Steps

After setup is complete:

1. Connect Gmail accounts via the Email Settings page
2. Configure business hours and auto-reply settings
3. Enable the email responder
4. Test by sending an email to the connected Gmail address

## Security Notes

- Client secrets are stored in Google Secret Manager
- Secrets are mounted as environment variables in Cloud Run (not exposed in logs)
- OAuth tokens are encrypted and stored in the database
- Each tenant's Gmail credentials are isolated

