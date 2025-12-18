#!/usr/bin/env python
"""Debug script to check conversations and messages."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, desc
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead

async def check_conversations():
    """Check conversations for tenant 4 (The Best Chatbot)."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CHECKING CONVERSATIONS FOR TENANT 4 (The Best Chatbot)")
        print("=" * 80)
        
        # Get recent conversations for tenant 4
        cutoff = datetime.utcnow() - timedelta(hours=24)
        conv_stmt = select(Conversation).where(
            Conversation.tenant_id == 4,
            Conversation.created_at >= cutoff
        ).order_by(desc(Conversation.created_at))
        
        result = await session.execute(conv_stmt)
        conversations = result.scalars().all()
        
        print(f"\nFound {len(conversations)} conversations for tenant 4 in last 24 hours:\n")
        
        if not conversations:
            print("No recent conversations found. Checking all conversations for tenant 4...")
            all_conv_stmt = select(Conversation).where(
                Conversation.tenant_id == 4
            ).order_by(desc(Conversation.created_at)).limit(10)
            all_result = await session.execute(all_conv_stmt)
            conversations = all_result.scalars().all()
            print(f"Found {len(conversations)} total conversations (showing last 10):\n")
        
        for conv in conversations:
            print(f"Conversation ID: {conv.id}")
            print(f"  Tenant ID: {conv.tenant_id}")
            print(f"  Channel: {conv.channel}")
            print(f"  Created: {conv.created_at}")
            print(f"  Updated: {conv.updated_at}")
            
            # Check for messages
            msg_stmt = select(Message).where(
                Message.conversation_id == conv.id
            ).order_by(Message.sequence_number)
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()
            
            print(f"  Messages: {len(messages)}")
            for msg in messages[:5]:  # Show first 5 messages
                content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                print(f"    [{msg.role}] {content_preview}")
            if len(messages) > 5:
                print(f"    ... and {len(messages) - 5} more messages")
            
            # Check for leads associated with this conversation
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
    asyncio.run(check_conversations())

