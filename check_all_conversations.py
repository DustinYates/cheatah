#!/usr/bin/env python
"""Debug script to check all recent conversations."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, desc
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead

async def check_all_conversations():
    """Check all recent conversations."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CHECKING ALL RECENT CONVERSATIONS (Last 24 hours)")
        print("=" * 80)
        
        # Get all recent conversations
        cutoff = datetime.utcnow() - timedelta(hours=24)
        conv_stmt = select(Conversation).where(
            Conversation.created_at >= cutoff
        ).order_by(desc(Conversation.created_at))
        
        result = await session.execute(conv_stmt)
        conversations = result.scalars().all()
        
        print(f"\nFound {len(conversations)} conversations in last 24 hours:\n")
        
        if not conversations:
            print("No recent conversations found. Checking all conversations...")
            all_conv_stmt = select(Conversation).order_by(desc(Conversation.created_at)).limit(20)
            all_result = await session.execute(all_conv_stmt)
            conversations = all_result.scalars().all()
            print(f"Found {len(conversations)} total conversations (showing last 20):\n")
        
        for conv in conversations:
            print(f"Conversation ID: {conv.id}")
            print(f"  Tenant ID: {conv.tenant_id}")
            print(f"  Channel: {conv.channel}")
            print(f"  Created: {conv.created_at}")
            print(f"  Updated: {conv.updated_at}")
            
            # Check for messages with "bob" or "bob@bob.com"
            msg_stmt = select(Message).where(
                Message.conversation_id == conv.id
            ).order_by(Message.sequence_number)
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()
            
            print(f"  Total Messages: {len(messages)}")
            
            # Look for messages containing "bob"
            bob_messages = [m for m in messages if "bob" in m.content.lower()]
            if bob_messages:
                print(f"  Messages containing 'bob': {len(bob_messages)}")
                for msg in bob_messages:
                    print(f"    [{msg.role}] {msg.content[:150]}")
            
            # Show last few messages
            if messages:
                print(f"  Last 3 messages:")
                for msg in messages[-3:]:
                    content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                    print(f"    [{msg.role}] {content_preview}")
            
            # Check for leads
            lead_stmt = select(Lead).where(Lead.conversation_id == conv.id)
            lead_result = await session.execute(lead_stmt)
            leads = lead_result.scalars().all()
            
            if leads:
                print(f"  Associated Leads: {len(leads)}")
                for lead in leads:
                    print(f"    Lead ID: {lead.id}, Name: {lead.name}, Email: {lead.email}")
            else:
                print(f"  Associated Leads: None")
            
            print("-" * 80)

if __name__ == "__main__":
    asyncio.run(check_all_conversations())

