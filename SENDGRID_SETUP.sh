#!/bin/bash

# SendGrid Integration Setup Guide
# ================================

# 1. Get SendGrid API Key
#    a. Go to https://app.sendgrid.com
#    b. Navigate to Settings → API Keys
#    c. Click "Create API Key"
#    d. Select "Full Access" or "Mail Send" permissions
#    e. Copy the generated API key

# 2. Add to .env file
#    SENDGRID_API_KEY=your_api_key_here
#    SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# 3. Files Created/Updated:
#    ✓ app/infrastructure/sendgrid_client.py - SendGrid client implementation
#    ✓ app/api/sendgrid_email.py - Email sending API endpoints
#    ✓ app/settings.py - Added SendGrid configuration
#    ✓ app/api/routes/__init__.py - Registered email routes
#    ✓ pyproject.toml - Added sendgrid dependency

# 4. Usage Examples:

# Using the client directly in Python:
# from app.infrastructure.sendgrid_client import get_sendgrid_client
#
# sendgrid = get_sendgrid_client()
# result = await sendgrid.send_email(
#     to_email="user@example.com",
#     subject="Welcome!",
#     html_content="<h1>Hello!</h1>",
#     text_content="Hello!",
#     from_email="support@yourdomain.com",
#     reply_to="support@yourdomain.com"
# )

# Using the API endpoint:
# POST /api/v1/sendgrid/email/send
# Content-Type: application/json
#
# {
#   "to_email": "user@example.com",
#   "subject": "Welcome!",
#   "html_content": "<h1>Hello!</h1>",
#   "text_content": "Hello!"
# }

# Response:
# {
#   "status": "success",
#   "message_id": "message-id-from-sendgrid",
#   "status_code": 202
# }

# 5. Verify Installation:
#    python3 -c "from sendgrid import SendGridAPIClient; print('SendGrid installed successfully')"

# 6. Optional: Testing with curl
#    curl -X POST http://localhost:8000/api/v1/sendgrid/email/send \
#      -H "Content-Type: application/json" \
#      -d '{
#        "to_email": "test@example.com",
#        "subject": "Test",
#        "html_content": "<p>Test email</p>"
#      }'
