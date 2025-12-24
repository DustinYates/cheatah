#!/bin/bash
# Script to verify Gmail OAuth configuration

set -e

PROJECT_ID="chatbots-466618"
REGION="us-central1"
SERVICE_NAME="chattercheatah"

echo "=========================================="
echo "Gmail OAuth Configuration Verification"
echo "=========================================="
echo ""

# Get configured values
echo "1. Checking Secret Manager values..."
CLIENT_ID=$(gcloud secrets versions access latest --secret=gmail-client-id --project=$PROJECT_ID 2>/dev/null)
echo "   Client ID: $CLIENT_ID"
echo ""

# Get Cloud Run environment variables
echo "2. Checking Cloud Run environment variables..."
REDIRECT_URI=$(gcloud run services describe $SERVICE_NAME \
  --project=$PROJECT_ID \
  --region=$REGION \
  --format=json 2>/dev/null | \
  python3 -c "import json,sys;d=json.load(sys.stdin);env=d.get('spec',{}).get('template',{}).get('spec',{}).get('containers',[{}])[0].get('env',[]);uri_vars=[e.get('value','') for e in env if e.get('name')=='GMAIL_OAUTH_REDIRECT_URI'];print(uri_vars[0] if uri_vars else 'NOT SET')")
echo "   Redirect URI: $REDIRECT_URI"
echo ""

# Expected values
EXPECTED_REDIRECT_URI="https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback"

echo "3. Verification:"
echo "   Expected Redirect URI: $EXPECTED_REDIRECT_URI"
if [ "$REDIRECT_URI" = "$EXPECTED_REDIRECT_URI" ]; then
    echo "   ✓ Redirect URI matches expected value"
else
    echo "   ✗ Redirect URI does NOT match!"
    echo "     Current: $REDIRECT_URI"
    echo "     Expected: $EXPECTED_REDIRECT_URI"
fi
echo ""

echo "4. Google Cloud Console Configuration:"
echo "   Go to: https://console.cloud.google.com/apis/credentials?project=$PROJECT_ID"
echo ""
echo "   Find OAuth 2.0 Client ID: $CLIENT_ID"
echo ""
echo "   Verify the 'Authorized redirect URIs' includes EXACTLY:"
echo "   $EXPECTED_REDIRECT_URI"
echo ""
echo "   Important:"
echo "   - Must be exact match (no trailing slash)"
echo "   - Must use https (not http)"
echo "   - Case-sensitive"
echo ""

if [ "$REDIRECT_URI" != "$EXPECTED_REDIRECT_URI" ]; then
    echo "5. Fix Cloud Run redirect URI..."
    read -p "   Update Cloud Run redirect URI now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gcloud run services update $SERVICE_NAME \
          --project=$PROJECT_ID \
          --region=$REGION \
          --update-env-vars="GMAIL_OAUTH_REDIRECT_URI=$EXPECTED_REDIRECT_URI" \
          2>&1
        echo "   ✓ Updated Cloud Run redirect URI"
    fi
fi

echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="

