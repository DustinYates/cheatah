"""Cleanup script to remove SMS conversations that were incorrectly saved as calls.

This script finds Call records that are actually SMS interactions (no duration,
no recording) and removes them from the calls table.

Usage:
    # Dry run (preview what would be deleted)
    python scripts/cleanup_sms_as_calls.py --dry-run

    # Actually delete the records
    python scripts/cleanup_sms_as_calls.py --delete
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta

# Add app to path
sys.path.insert(0, "/Users/dustinyates/Desktop/chattercheetah")

from sqlalchemy import select, delete
from sqlalchemy.orm import joinedload

from app.persistence.database import async_session_factory
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary


async def find_sms_calls():
    """Find Call records that are likely SMS (no duration, no recording)."""
    async with async_session_factory() as db:
        # Find calls with no duration and no recording - likely SMS
        stmt = (
            select(Call)
            .options(joinedload(Call.summary))
            .where(
                (Call.duration == None) | (Call.duration == 0),
                Call.recording_url == None,
            )
            .order_by(Call.created_at.desc())
        )

        result = await db.execute(stmt)
        calls = result.unique().scalars().all()

        return calls


async def delete_call(call_id: int):
    """Delete a call record and its summary."""
    async with async_session_factory() as db:
        # First delete the summary if it exists
        await db.execute(
            delete(CallSummary).where(CallSummary.call_id == call_id)
        )

        # Then delete the call
        await db.execute(
            delete(Call).where(Call.id == call_id)
        )

        await db.commit()


async def main():
    parser = argparse.ArgumentParser(description="Clean up SMS records incorrectly saved as calls")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be deleted")
    parser.add_argument("--delete", action="store_true", help="Actually delete the records")
    args = parser.parse_args()

    if not args.dry_run and not args.delete:
        print("Please specify --dry-run or --delete")
        return

    print("Finding Call records that are likely SMS (no duration, no recording)...")
    calls = await find_sms_calls()

    if not calls:
        print("No suspicious call records found.")
        return

    print(f"\nFound {len(calls)} potential SMS-as-call records:\n")
    print(f"{'ID':<8} {'Phone':<18} {'Duration':<10} {'Created':<20} {'Intent':<15} {'Outcome':<15}")
    print("-" * 90)

    for call in calls:
        intent = call.summary.intent if call.summary else "N/A"
        outcome = call.summary.outcome if call.summary else "N/A"
        duration = str(call.duration) if call.duration else "-"
        created = call.created_at.strftime("%Y-%m-%d %H:%M") if call.created_at else "N/A"

        print(f"{call.id:<8} {call.from_number:<18} {duration:<10} {created:<20} {intent:<15} {outcome:<15}")

    print()

    if args.dry_run:
        print("DRY RUN - No records deleted. Use --delete to actually remove these records.")
    elif args.delete:
        confirm = input(f"Delete {len(calls)} records? (yes/no): ")
        if confirm.lower() == "yes":
            for call in calls:
                print(f"Deleting call {call.id} ({call.from_number})...")
                await delete_call(call.id)
            print(f"\nDeleted {len(calls)} records.")
        else:
            print("Aborted.")


if __name__ == "__main__":
    asyncio.run(main())
