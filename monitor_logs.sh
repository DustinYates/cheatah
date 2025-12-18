#!/bin/bash
# Script to help monitor application logs for lead extraction

echo "=" | tr '=' '\n' | head -80
echo "CHATTER CHEETAH LOG MONITOR"
echo "=" | tr '=' '\n' | head -80
echo ""
echo "This script helps you monitor logs for lead extraction."
echo ""
echo "After starting your server with:"
echo "  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Look for these log messages when testing the chatbot:"
echo ""
echo "✅ SUCCESS INDICATORS:"
echo "  - 'Lead auto-captured from conversation' - Lead was created successfully"
echo "  - 'Extracted contact info: name=..., email=..., phone=...' - Extraction worked"
echo ""
echo "🔍 DEBUG INFO (if LOG_LEVEL=DEBUG):"
echo "  - 'Regex extraction results' - Shows what regex patterns found"
echo "  - 'Checking for existing lead' - Shows lead check is happening"
echo "  - 'No existing lead found, attempting extraction' - Extraction is starting"
echo ""
echo "❌ ERROR INDICATORS:"
echo "  - 'Contact extraction failed' - LLM extraction failed (regex fallback should still work)"
echo "  - 'Failed to parse contact extraction response' - JSON parsing issue"
echo "  - 'Failed to capture lead after extraction' - Lead creation failed"
echo ""
echo "📝 TEST MESSAGE:"
echo "  Send this in the chat: 'can i swim im bob boberson bob@bob.com'"
echo ""
echo "=" | tr '=' '\n' | head -80
echo ""
echo "To filter logs in real-time, use:"
echo "  tail -f your-log-file.log | grep -i 'lead\\|extract\\|bob'"
echo ""
echo "Or if logs are in terminal, just watch the terminal output."
echo ""

