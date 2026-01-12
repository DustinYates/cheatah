#!/bin/bash
# Watch for Telnyx SMS activity triggered by email

echo "=========================================="
echo "   TELNYX SMS MONITORING"
echo "=========================================="
echo ""
echo "Monitoring Cloud Run logs for:"
echo "  ✉️  Email webhook processing"
echo "  📧 Email body parsing"
echo "  📱 Telnyx SMS sending"
echo "  ☎️  Phone number handling"
echo ""
echo "Waiting for email to arrive..."
echo ""

# Watch the Cloud Run logs output file
tail -f /tmp/claude/tasks/b8215f0.output | grep --line-buffered -iE "email_webhook|EMAIL_BODY|telnyx|send.*sms|phone|text.*message" | while read line; do
    timestamp=$(date '+%H:%M:%S')
    echo "[$timestamp] $line"
done
