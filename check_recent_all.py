#!/usr/bin/env python
"""Check ALL conversations regardless of time to find the bob conversation."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, desc
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead

async def check_all():
    """Check all conversations for tenant 1 looking for bob."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("SEARCHING ALL CONVERSATIONS FOR TENANT 1 (Looking for 'bob')")
        print("=" * 80)
        
        # Get ALL conversations for tenant 1
        conv_stmt = select(Conversation).where(
            Conversation.tenant_id == 1
        ).order_by(desc(Conversation.created_at))
        
        result = await session.execute(conv_stmt)
        conversations = result.scalars().all()
        
        print(f"\nFound {len(conversations)} total conversations for tenant 1\n")
        
        for conv in conversations:
            # Get all messages
            msg_stmt = select(Message).where(
                Message.conversation_id == conv.id
            ).order_by(Message.sequence_number)
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()
            
            # Check if any message contains "bob" or email patterns
            has_bob = False
            for msg in messages:
                if "bob" in msg.content.lower() or "bob@bob.com" in msg.content.lower() or "boberson" in msg.content.lower():
                    has_bob = True
                    print(f"Conversation ID: {conv.id}")
                    print(f"  Created: {conv.created_at}")
                    print(f"  Updated: {conv.updated_at}")
                    print(f"  Messages containing 'bob':")
                    for m in messages:
                        if "bob" in m.content.lower() or "@" in m.content:
                            print(f"    [{m.role}] {m.content}")
                    
                    # Check for leads
                    lead_stmt = select(Lead).where(Lead.conversation_id == conv.id)
                    lead_result = await session.execute(lead_stmt)
                    leads = lead_result.scalars().all()
                    
                    if leads:
                        print(f"  ✓ ASSOCIATED LEADS: {len(leads)}")
                        for lead in leads:
                            print(f"    Lead ID: {lead.id}, Name: {lead.name}, Email: {lead.email}")
                    else:
                        print(f"  ✗ NO LEADS ASSOCIATED WITH THIS CONVERSATION")
                    print("-" * 80)
                    break
        
        # Check if we found any bob conversations
        found_bob = False
        for conv in conversations:
            msg_stmt = select(Message).where(Message.conversation_id == conv.id)
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()
            if any("bob" in msg.content.lower() for msg in messages):
                found_bob = True
                break
        
        if not found_bob:
            print("\n⚠️  No conversations found with 'bob' in any message")
            print("This suggests:")
            print("  1. The conversation hasn't been saved to the database yet")
            print("  2. The server needs to be restarted with the new code")
            print("  3. The chat is using a different database/environment")
            print("\n💡 RECOMMENDATION: Restart your server to ensure the new code is running")

if __name__ == "__main__":
    asyncio.run(check_all())

