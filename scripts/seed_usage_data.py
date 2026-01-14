"""Seed sample usage data for analytics testing.

This script creates sample conversations, messages, and calls
to populate the Usage Analytics dashboard after a database reset.

Usage:
    python scripts/seed_usage_data.py [tenant_id]

If no tenant_id is provided, it will use the first active tenant found.
"""

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.persistence.database import AsyncSessionLocal
from app.persistence.models.call import Call
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant import Tenant


async def get_tenant(db, tenant_id: int | None = None):
    """Get the target tenant for seeding."""
    if tenant_id:
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant:
            return tenant
        print(f"Tenant with ID {tenant_id} not found.")

    # Get first active tenant
    result = await db.execute(
        select(Tenant).where(Tenant.is_active == True).order_by(Tenant.id)
    )
    tenant = result.scalars().first()
    return tenant


async def seed_sms_conversations(db, tenant_id: int, days: int = 14):
    """Create sample SMS conversations with messages."""
    print(f"\n📱 Creating SMS conversations for tenant {tenant_id}...")

    conversations_created = 0
    messages_created = 0

    for day_offset in range(days):
        # Create 2-5 SMS conversations per day
        num_conversations = random.randint(2, 5)
        base_date = datetime.utcnow() - timedelta(days=day_offset)

        for _ in range(num_conversations):
            # Random time within the day
            random_hours = random.randint(8, 20)  # 8 AM to 8 PM
            random_minutes = random.randint(0, 59)
            conv_time = base_date.replace(hour=random_hours, minute=random_minutes, second=0, microsecond=0)

            # Create conversation
            phone = f"+1{random.randint(2000000000, 9999999999)}"
            conversation = Conversation(
                tenant_id=tenant_id,
                channel="sms",
                external_id=f"sms_{uuid.uuid4().hex[:16]}",
                phone_number=phone,
                created_at=conv_time,
                updated_at=conv_time,
            )
            db.add(conversation)
            await db.flush()
            conversations_created += 1

            # Create 2-6 messages per conversation (alternating user/assistant)
            num_messages = random.randint(2, 6)
            for seq in range(num_messages):
                role = "user" if seq % 2 == 0 else "assistant"
                msg_time = conv_time + timedelta(minutes=seq * 2)

                content = (
                    f"Sample {role} message {seq + 1}" if role == "user"
                    else f"Thank you for your message! How can I help you today?"
                )

                message = Message(
                    conversation_id=conversation.id,
                    role=role,
                    content=content,
                    sequence_number=seq,
                    created_at=msg_time,
                )
                db.add(message)
                messages_created += 1

    await db.commit()
    print(f"   ✓ Created {conversations_created} SMS conversations with {messages_created} messages")
    return conversations_created, messages_created


async def seed_web_conversations(db, tenant_id: int, days: int = 14):
    """Create sample web chatbot conversations."""
    print(f"\n�� Creating web chat conversations for tenant {tenant_id}...")

    conversations_created = 0
    messages_created = 0

    for day_offset in range(days):
        # Create 5-15 web chat conversations per day
        num_conversations = random.randint(5, 15)
        base_date = datetime.utcnow() - timedelta(days=day_offset)

        for _ in range(num_conversations):
            random_hours = random.randint(0, 23)
            random_minutes = random.randint(0, 59)
            conv_time = base_date.replace(hour=random_hours, minute=random_minutes, second=0, microsecond=0)

            conversation = Conversation(
                tenant_id=tenant_id,
                channel="web",
                external_id=f"web_{uuid.uuid4().hex[:16]}",
                created_at=conv_time,
                updated_at=conv_time,
            )
            db.add(conversation)
            await db.flush()
            conversations_created += 1

            # Web chats typically have more messages (3-10)
            num_messages = random.randint(3, 10)
            for seq in range(num_messages):
                role = "user" if seq % 2 == 0 else "assistant"
                msg_time = conv_time + timedelta(seconds=seq * 30)

                message = Message(
                    conversation_id=conversation.id,
                    role=role,
                    content=f"Sample web {role} message {seq + 1}",
                    sequence_number=seq,
                    created_at=msg_time,
                )
                db.add(message)
                messages_created += 1

    await db.commit()
    print(f"   ✓ Created {conversations_created} web conversations with {messages_created} messages")
    return conversations_created, messages_created


async def seed_calls(db, tenant_id: int, days: int = 14):
    """Create sample voice call records."""
    print(f"\n📞 Creating call records for tenant {tenant_id}...")

    calls_created = 0
    total_minutes = 0

    for day_offset in range(days):
        # Create 1-4 calls per day
        num_calls = random.randint(1, 4)
        base_date = datetime.utcnow() - timedelta(days=day_offset)

        for _ in range(num_calls):
            random_hours = random.randint(9, 17)  # Business hours
            random_minutes = random.randint(0, 59)
            call_start = base_date.replace(hour=random_hours, minute=random_minutes, second=0, microsecond=0)

            # Call duration: 30 seconds to 15 minutes
            duration_seconds = random.randint(30, 900)
            call_end = call_start + timedelta(seconds=duration_seconds)

            call = Call(
                tenant_id=tenant_id,
                call_sid=f"CA{uuid.uuid4().hex[:32]}",
                from_number=f"+1{random.randint(2000000000, 9999999999)}",
                to_number=f"+1{random.randint(2000000000, 9999999999)}",
                status="completed",
                direction="inbound",
                started_at=call_start,
                ended_at=call_end,
                duration=duration_seconds,
                created_at=call_start,
                updated_at=call_end,
            )
            db.add(call)
            calls_created += 1
            total_minutes += duration_seconds / 60

    await db.commit()
    print(f"   ✓ Created {calls_created} calls totaling {total_minutes:.1f} minutes")
    return calls_created, total_minutes


async def seed_usage_data(tenant_id: int | None = None, days: int = 14):
    """Main function to seed all usage data."""
    print("=" * 60)
    print("🌱 Seeding Usage Analytics Data")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # Get target tenant
        tenant = await get_tenant(db, tenant_id)

        if not tenant:
            print("\n❌ No active tenant found. Please create a tenant first.")
            print("   Run: python scripts/create_test_tenant.py")
            return

        print(f"\n🎯 Target Tenant: {tenant.name} (ID: {tenant.id})")
        print(f"   Seeding {days} days of data...")

        # Seed all data types
        sms_convs, sms_msgs = await seed_sms_conversations(db, tenant.id, days)
        web_convs, web_msgs = await seed_web_conversations(db, tenant.id, days)
        calls, call_mins = await seed_calls(db, tenant.id, days)

        # Summary
        print("\n" + "=" * 60)
        print("✅ SEEDING COMPLETE!")
        print("=" * 60)
        print(f"\n📊 Summary for tenant '{tenant.name}':")
        print(f"   SMS Conversations: {sms_convs}")
        print(f"   SMS Messages:      {sms_msgs}")
        print(f"   Web Conversations: {web_convs}")
        print(f"   Web Messages:      {web_msgs}")
        print(f"   Voice Calls:       {calls}")
        print(f"   Call Minutes:      {call_mins:.1f}")
        print(f"\n🔄 Refresh your Usage Analytics page to see the data!")


if __name__ == "__main__":
    # Parse optional tenant_id from command line
    tenant_id = None
    days = 14

    if len(sys.argv) > 1:
        try:
            tenant_id = int(sys.argv[1])
        except ValueError:
            print(f"Invalid tenant_id: {sys.argv[1]}")
            sys.exit(1)

    if len(sys.argv) > 2:
        try:
            days = int(sys.argv[2])
        except ValueError:
            print(f"Invalid days: {sys.argv[2]}")
            sys.exit(1)

    asyncio.run(seed_usage_data(tenant_id, days))
