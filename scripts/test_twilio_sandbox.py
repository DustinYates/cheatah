"""Test script for Twilio sandbox integration."""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.domain.services.sms_service import SmsService
from app.infrastructure.twilio_client import TwilioSmsClient
from app.persistence.database import AsyncSessionLocal
from app.settings import settings


async def test_twilio_sandbox():
    """Test Twilio sandbox integration."""
    print("Testing Twilio Sandbox Integration")
    print("=" * 50)
    
    # Initialize Twilio client
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        print("ERROR: Twilio credentials not configured")
        print("Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables")
        return
    
    twilio_client = TwilioSmsClient()
    print(f"✓ Twilio client initialized")
    
    # Test sending SMS (use sandbox number)
    test_phone = os.getenv("TEST_PHONE_NUMBER", "+1234567890")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER", settings.twilio_account_sid)
    
    print(f"\nSending test SMS to {test_phone} from {twilio_number}")
    
    try:
        result = twilio_client.send_sms(
            to=test_phone,
            from_=twilio_number,
            body="Test message from Chatter Cheetah SMS service",
        )
        print(f"✓ SMS sent successfully")
        print(f"  Message SID: {result.get('sid')}")
        print(f"  Status: {result.get('status')}")
    except Exception as e:
        print(f"✗ Failed to send SMS: {e}")
    
    # Test SMS service processing
    print(f"\nTesting SMS service processing...")
    async with AsyncSessionLocal() as session:
        sms_service = SmsService(session)
        
        # Test compliance handling
        from app.domain.services.compliance_handler import ComplianceHandler
        handler = ComplianceHandler()
        
        test_messages = ["STOP", "HELP", "START", "Hello, I need help"]
        for msg in test_messages:
            result = handler.check_compliance(msg)
            print(f"  '{msg}' -> {result.action}")
    
    print("\n" + "=" * 50)
    print("Test complete")


if __name__ == "__main__":
    asyncio.run(test_twilio_sandbox())

