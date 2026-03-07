#!/usr/bin/env python3
"""DEPRECATED: Manual testing script for voice functionality.

This script was for testing Twilio-based voice webhooks (Phase 0).
Voice is now handled by Telnyx AI Assistant. Test voice by calling
the tenant's assigned phone number directly.

See docs/NEW_TENANT_SETUP.md for voice testing instructions.
"""

import asyncio
import sys


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
                print(f"\nFound {len(calls)} recent call(s):\n")
                for call in calls:
                    print(f"  Call ID: {call.id}")
                    print(f"  SID: {call.call_sid}")
                    print(f"  From: {call.from_number} -> To: {call.to_number}")
                    print(f"  Status: {call.status}, Duration: {call.duration}s")
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
        print("Business hours service test PASSED")
    else:
        print("Business hours service test FAILED")


async def run_all_tests():
    """Run all manual tests."""
    print("=" * 60)
    print("Running Voice manual tests")
    print("=" * 60)

    await test_business_hours()
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
        print("  check_calls    - Check calls in database")
        print("  test_hours     - Test business hours service")
        return

    command = sys.argv[1]

    if command == "all":
        asyncio.run(run_all_tests())
    elif command == "check_calls":
        asyncio.run(check_database_calls())
    elif command == "test_hours":
        asyncio.run(test_business_hours())
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()

