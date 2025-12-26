#!/bin/bash
# Quick login script - tries local first, then production

EMAIL="dustin.yates@gmail.com"
PASSWORD="Hudlink2168"

echo "Attempting login..."
echo "Email: $EMAIL"
echo ""

# Try local first
echo "Trying local server (http://localhost:8000)..."
LOCAL_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

LOCAL_HTTP_CODE=$(echo "$LOCAL_RESPONSE" | tail -n1)
LOCAL_BODY=$(echo "$LOCAL_RESPONSE" | sed '$d')

if [ "$LOCAL_HTTP_CODE" = "200" ]; then
  echo "✓ Login successful on local server!"
  echo "$LOCAL_BODY" | python3 -m json.tool
  echo ""
  echo "Token saved above. Copy the 'access_token' value."
  exit 0
else
  echo "Local server failed (HTTP $LOCAL_HTTP_CODE)"
  echo "$LOCAL_BODY"
  echo ""
fi

# Try production
echo "Trying production server..."
PROD_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://chattercheatah-900139201687.us-central1.run.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

PROD_HTTP_CODE=$(echo "$PROD_RESPONSE" | tail -n1)
PROD_BODY=$(echo "$PROD_RESPONSE" | sed '$d')

if [ "$PROD_HTTP_CODE" = "200" ]; then
  echo "✓ Login successful on production server!"
  echo "$PROD_BODY" | python3 -m json.tool
  echo ""
  echo "Token saved above. Copy the 'access_token' value."
  exit 0
else
  echo "Production server failed (HTTP $PROD_HTTP_CODE)"
  echo "$PROD_BODY"
  echo ""
  echo "❌ Login failed on both servers. Please check:"
  echo "   1. Is the server running locally? (uv run uvicorn app.main:app --reload)"
  echo "   2. Was the tenant created in the same database as the server?"
  echo "   3. Is the email/password correct?"
  exit 1
fi

