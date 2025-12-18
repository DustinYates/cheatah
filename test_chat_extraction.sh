#!/bin/bash
# Script to test chat endpoint and check if lead extraction works

echo "Testing Chat Endpoint for Lead Extraction"
echo "=========================================="
echo ""

# Test with contact info in message
echo "Sending test message with contact info: 'can i swim im bob boberson bob@bob.com'"
echo ""

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": 1,
    "message": "can i swim im bob boberson bob@bob.com"
  }')

http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
response_body=$(echo "$response" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $http_code"
echo "Response:"
if [ -n "$response_body" ]; then
  echo "$response_body" | python3 -m json.tool 2>/dev/null || echo "$response_body"
else
  echo "(Empty response - server may not be running)"
fi
echo ""

# Check database for the lead
echo "Checking database for new lead..."
echo ""

cd /Users/dustinyates/cheatah/cheatah-1
uv run python check_tenant1.py 2>&1 | tail -50

