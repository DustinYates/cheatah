#!/usr/bin/env python3
"""Manual testing script for voice functionality.

This script provides commands for manual testing of the voice assistant
Phase 0 implementation against the running API.

Usage:
    # Start the server first
    uvicorn app.main:app --reload

    # Then run tests
    python scripts/test_voice_manual.py test_inbound
    python scripts/test_voice_manual.py test_status
    python scripts/test_voice_manual.py check_calls
"""

import asyncio
import sys
import httpx


API_BASE = "http://localhost:8000/api/v1"


async def test_inbound_webhook():
    """Test inbound call webhook."""
    print("Testing inbound call webhook...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE}/voice/inbound",
            data={
                "CallSid": "CA_MANUAL_TEST_001",
                "From": "+1234567890",
                "To": "+0987654321",
                "CallStatus": "ringing",
                "AccountSid": "AC_MANUAL_TEST",
            },
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response:\n{response.text[:500]}...")
        
        if response.status_code == 200 and "<?xml" in response.text:
            print("✅ Inbound webhook test PASSED")
        else:
            print("❌ Inbound webhook test FAILED")


async def test_status_webhook():
    """Test call status webhook."""
    print("Testing call status webhook...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE}/voice/status",
            data={
                "CallSid": "CA_MANUAL_TEST_001",
                "CallStatus": "completed",
                "CallDuration": "120",
                "RecordingSid": "RE_MANUAL_TEST",
                "RecordingUrl": "https://api.twilio.com/test-recording",
            },
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Status webhook test PASSED")
        else:
            print("❌ Status webhook test FAILED")


async def check_database_calls():
    """Check calls in the database."""
    print("Checking calls in database...")
    
    try:
        from app.persistence.database import AsyncSessionLocal
        from app.persistence.models.call import Call
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            stmt = select(Call).order_by(Call.created_at.desc()).limit(10)
            result = await session.execute(stmt)
            calls = result.scalars().all()
            
            if calls:
                print(f"\n📞 Found {len(calls)} recent call(s):\n")
                for call in calls:
                    print(f"  Call ID: {call.id}")
                    print(f"  SID: {call.call_sid}")
                    print(f"  From: {call.from_number} -> To: {call.to_number}")
                    print(f"  Status: {call.status}, Duration: {call.duration}s")
                    print(f"  Recording: {call.recording_sid or 'None'}")
                    print(f"  Started: {call.started_at}")
                    print(f"  Ended: {call.ended_at}")
                    print("-" * 40)
            else:
                print("No calls found in database.")
                
    except Exception as e:
        print(f"Error accessing database: {e}")
        print("Make sure DATABASE_URL is configured.")


async def test_business_hours():
    """Test business hours service."""
    print("Testing business hours service...")
    
    from app.domain.services.business_hours_service import is_within_business_hours
    from datetime import datetime
    
    # Current time check
    result = is_within_business_hours(
        business_hours={
            "monday": {"start": "09:00", "end": "17:00"},
            "tuesday": {"start": "09:00", "end": "17:00"},
            "wednesday": {"start": "09:00", "end": "17:00"},
            "thursday": {"start": "09:00", "end": "17:00"},
            "friday": {"start": "09:00", "end": "17:00"},
        },
        timezone_str="UTC",
        business_hours_enabled=True,
    )
    
    now = datetime.now()
    print(f"Current time: {now.strftime('%A %H:%M')}")
    print(f"Within business hours: {result}")
    
    # Test disabled
    result_disabled = is_within_business_hours(
        business_hours={"monday": {"start": "09:00", "end": "17:00"}},
        timezone_str="UTC",
        business_hours_enabled=False,
    )
    print(f"Disabled check returns True: {result_disabled}")
    
    if result_disabled:
        print("✅ Business hours service test PASSED")
    else:
        print("❌ Business hours service test FAILED")


async def test_twiml_generation():
    """Test TwiML generation."""
    print("Testing TwiML generation...")
    
    from app.api.routes.voice_webhooks import (
        _generate_open_hours_twiml,
        _generate_voicemail_twiml,
    )
    
    open_twiml = _generate_open_hours_twiml()
    voicemail_twiml = _generate_voicemail_twiml()
    
    print("\n📝 Open Hours TwiML:")
    print(open_twiml)
    
    print("\n📝 Voicemail TwiML:")
    print(voicemail_twiml)
    
    # Validate XML structure
    valid_open = "<?xml" in open_twiml and "<Response>" in open_twiml
    valid_voicemail = "<?xml" in voicemail_twiml and "<Record" in voicemail_twiml
    
    if valid_open and valid_voicemail:
        print("\n✅ TwiML generation test PASSED")
    else:
        print("\n❌ TwiML generation test FAILED")


async def run_all_tests():
    """Run all manual tests."""
    print("=" * 60)
    print("Running all Voice Phase 0 manual tests")
    print("=" * 60)
    
    await test_business_hours()
    print()
    
    await test_twiml_generation()
    print()
    
    await test_inbound_webhook()
    print()
    
    await test_status_webhook()
    print()
    
    await check_database_calls()
    
    print("\n" + "=" * 60)
    print("Manual tests completed!")
    print("=" * 60)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_voice_manual.py <command>")
        print("\nCommands:")
        print("  all            - Run all tests")
        print("  test_inbound   - Test inbound call webhook")
        print("  test_status    - Test call status webhook")
        print("  check_calls    - Check calls in database")
        print("  test_hours     - Test business hours service")
        print("  test_twiml     - Test TwiML generation")
        return

    command = sys.argv[1]
    
    if command == "all":
        asyncio.run(run_all_tests())
    elif command == "test_inbound":
        asyncio.run(test_inbound_webhook())
    elif command == "test_status":
        asyncio.run(test_status_webhook())
    elif command == "check_calls":
        asyncio.run(check_database_calls())
    elif command == "test_hours":
        asyncio.run(test_business_hours())
    elif command == "test_twiml":
        asyncio.run(test_twiml_generation())
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()

