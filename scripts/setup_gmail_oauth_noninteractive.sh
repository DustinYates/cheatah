#!/bin/bash
# Non-interactive setup script for Gmail OAuth credentials
# Usage: CLIENT_ID=xxx CLIENT_SECRET=yyy ./setup_gmail_oauth_noninteractive.sh

set -e

PROJECT_ID="chatbots-466618"
SERVICE_NAME="chattercheatah"
REGION="us-central1"
REDIRECT_URI="https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback"

# Get credentials from environment variables
CLIENT_ID="${GMAIL_CLIENT_ID:-${CLIENT_ID}}"
CLIENT_SECRET="${GMAIL_CLIENT_SECRET:-${CLIENT_SECRET}}"

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
    echo "Error: GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET environment variables are required"
    echo ""
    echo "Usage:"
    echo "  GMAIL_CLIENT_ID=your-client-id GMAIL_CLIENT_SECRET=your-client-secret ./scripts/setup_gmail_oauth_noninteractive.sh"
    echo ""
    echo "Or export them first:"
    echo "  export GMAIL_CLIENT_ID=your-client-id"
    echo "  export GMAIL_CLIENT_SECRET=your-client-secret"
    echo "  ./scripts/setup_gmail_oauth_noninteractive.sh"
    exit 1
fi

echo "=========================================="
echo "Gmail OAuth Setup for Chatter Cheetah"
echo "=========================================="
echo ""
echo "Step 1: Creating GCP Secrets..."
echo "--------------------------------"

# Create or update secrets
echo -n "$CLIENT_ID" | gcloud secrets create gmail-client-id \
    --data-file=- \
    --project=${PROJECT_ID} \
    2>/dev/null || echo -n "$CLIENT_ID" | gcloud secrets versions add gmail-client-id \
    --data-file=- \
    --project=${PROJECT_ID}

echo "✓ Created/updated gmail-client-id secret"

echo -n "$CLIENT_SECRET" | gcloud secrets create gmail-client-secret \
    --data-file=- \
    --project=${PROJECT_ID} \
    2>/dev/null || echo -n "$CLIENT_SECRET" | gcloud secrets versions add gmail-client-secret \
    --data-file=- \
    --project=${PROJECT_ID}

echo "✓ Created/updated gmail-client-secret secret"

echo ""
echo "Step 2: Granting Cloud Run Access..."
echo "--------------------------------------"

# Grant Cloud Run service account access to secrets
SERVICE_ACCOUNT=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || echo "")

if [ -z "$SERVICE_ACCOUNT" ]; then
    SERVICE_ACCOUNT="${PROJECT_ID}@appspot.gserviceaccount.com"
fi

echo "Granting secret access to: ${SERVICE_ACCOUNT}"

gcloud secrets add-iam-policy-binding gmail-client-id \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=${PROJECT_ID} \
    2>/dev/null && echo "✓ Granted access to gmail-client-id" || echo "⚠ Access already granted for gmail-client-id"

gcloud secrets add-iam-policy-binding gmail-client-secret \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=${PROJECT_ID} \
    2>/dev/null && echo "✓ Granted access to gmail-client-secret" || echo "⚠ Access already granted for gmail-client-secret"

echo ""
echo "Step 3: Updating Cloud Run Service..."
echo "--------------------------------------"

# Update Cloud Run service with secrets and environment variables
gcloud run services update ${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --update-secrets="GMAIL_CLIENT_ID=gmail-client-id:latest,GMAIL_CLIENT_SECRET=gmail-client-secret:latest" \
    --update-env-vars="GMAIL_OAUTH_REDIRECT_URI=${REDIRECT_URI},GMAIL_PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/gmail-push-notifications" \
    --quiet

echo "✓ Updated Cloud Run service configuration"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "The Gmail OAuth integration is now configured."
echo "Cloud Run is deploying a new revision with the Gmail settings..."
echo ""
echo "Next steps:"
echo "1. Wait 1-2 minutes for Cloud Run to deploy"
echo "2. Go to: https://chattercheatah-frontend-900139201687.us-central1.run.app/email"
echo "3. Click 'Connect Gmail' to test the integration"
echo ""

