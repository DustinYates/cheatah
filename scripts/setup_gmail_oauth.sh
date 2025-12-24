#!/bin/bash
# Setup script for Gmail OAuth credentials
# This script helps configure Gmail OAuth for the email responder

set -e

PROJECT_ID="chatbots-466618"
SERVICE_NAME="chattercheatah"
REGION="us-central1"
REDIRECT_URI="https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback"

echo "=========================================="
echo "Gmail OAuth Setup for Chatter Cheetah"
echo "=========================================="
echo ""
echo "Step 1: Create OAuth 2.0 Credentials"
echo "--------------------------------------"
echo "1. Go to: https://console.cloud.google.com/apis/credentials?project=${PROJECT_ID}"
echo "2. Click '+ CREATE CREDENTIALS' → 'OAuth client ID'"
echo "3. If prompted, configure OAuth consent screen:"
echo "   - User Type: External (or Internal if using Google Workspace)"
echo "   - App name: Chatter Cheetah"
echo "   - User support email: your-email@example.com"
echo "   - Developer contact: your-email@example.com"
echo "   - Click 'Save and Continue' through the scopes (no need to add scopes here)"
echo "   - Add test users if needed"
echo ""
echo "4. Create OAuth Client ID:"
echo "   - Application type: Web application"
echo "   - Name: Chatter Cheetah Gmail Client"
echo "   - Authorized redirect URIs:"
echo "     ${REDIRECT_URI}"
echo "   - Click 'CREATE'"
echo ""
echo "5. Copy the Client ID and Client Secret"
echo ""
read -p "Enter the Client ID: " CLIENT_ID
read -sp "Enter the Client Secret: " CLIENT_SECRET
echo ""

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
    echo "Error: Client ID and Client Secret are required"
    exit 1
fi

echo ""
echo "Step 2: Creating GCP Secrets..."
echo "--------------------------------"

# Create or update secrets
echo -n "$CLIENT_ID" | gcloud secrets create gmail-client-id \
    --data-file=- \
    --project=${PROJECT_ID} \
    2>/dev/null || echo -n "$CLIENT_ID" | gcloud secrets versions add gmail-client-id \
    --data-file=- \
    --project=${PROJECT_ID}

echo -n "$CLIENT_SECRET" | gcloud secrets create gmail-client-secret \
    --data-file=- \
    --project=${PROJECT_ID} \
    2>/dev/null || echo -n "$CLIENT_SECRET" | gcloud secrets versions add gmail-client-secret \
    --data-file=- \
    --project=${PROJECT_ID}

echo ""
echo "Step 3: Updating Cloud Run Service..."
echo "--------------------------------------"

# Grant Cloud Run service account access to secrets
SERVICE_ACCOUNT=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --format="value(spec.template.spec.serviceAccountName)" || echo "")

if [ -z "$SERVICE_ACCOUNT" ]; then
    SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

echo "Granting secret access to: ${SERVICE_ACCOUNT}"

gcloud secrets add-iam-policy-binding gmail-client-id \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=${PROJECT_ID} \
    2>/dev/null || echo "Access already granted"

gcloud secrets add-iam-policy-binding gmail-client-secret \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=${PROJECT_ID} \
    2>/dev/null || echo "Access already granted"

# Update Cloud Run service with secrets and environment variables
echo "Updating Cloud Run service..."

gcloud run services update ${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --update-secrets="GMAIL_CLIENT_ID=gmail-client-id:latest,GMAIL_CLIENT_SECRET=gmail-client-secret:latest" \
    --update-env-vars="GMAIL_OAUTH_REDIRECT_URI=${REDIRECT_URI},GMAIL_PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/gmail-push-notifications"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "The Gmail OAuth integration is now configured."
echo "You can now connect Gmail accounts in the Email Settings page."
echo ""
echo "Note: If this is the first time setting up OAuth consent screen,"
echo "you may need to add test users or wait for verification."
echo ""

