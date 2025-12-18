#!/usr/bin/env python
"""Debug script to check tenant 1 conversations and leads."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, desc, or_
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead

async def check_tenant1():
    """Check conversations and leads for tenant 1."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CHECKING TENANT 1 (Recent Activity)")
        print("=" * 80)
        
        # Get recent conversations for tenant 1
        cutoff = datetime.utcnow() - timedelta(hours=2)  # Last 2 hours
        conv_stmt = select(Conversation).where(
            Conversation.tenant_id == 1,
            Conversation.created_at >= cutoff
        ).order_by(desc(Conversation.created_at))
        
        result = await session.execute(conv_stmt)
        conversations = result.scalars().all()
        
        print(f"\nFound {len(conversations)} conversations for tenant 1 in last 2 hours:\n")
        
        if not conversations:
            print("No recent conversations. Checking last 10 conversations...")
            all_conv_stmt = select(Conversation).where(
                Conversation.tenant_id == 1
            ).order_by(desc(Conversation.created_at)).limit(10)
            all_result = await session.execute(all_conv_stmt)
            conversations = all_result.scalars().all()
            print(f"Found {len(conversations)} total conversations:\n")
        
        for conv in conversations:
            print(f"Conversation ID: {conv.id}")
            print(f"  Created: {conv.created_at}")
            print(f"  Updated: {conv.updated_at}")
            
            # Get all messages
            msg_stmt = select(Message).where(
                Message.conversation_id == conv.id
            ).order_by(Message.sequence_number)
            msg_result = await session.execute(msg_stmt)
            messages = msg_result.scalars().all()
            
            print(f"  Messages: {len(messages)}")
            
            # Look for messages containing "bob" or email patterns
            for msg in messages:
                content_lower = msg.content.lower()
                if "bob" in content_lower or "@" in msg.content or "boberson" in content_lower:
                    print(f"    [{msg.role}] {msg.content[:200]}")
            
            # Show last message if no bob found
            if messages and not any("bob" in m.content.lower() or "@" in m.content for m in messages):
                last_msg = messages[-1]
                print(f"    Last message [{last_msg.role}]: {last_msg.content[:150]}")
            
            # Check for leads
            lead_stmt = select(Lead).where(Lead.conversation_id == conv.id)
            lead_result = await session.execute(lead_stmt)
            leads = lead_result.scalars().all()
            
            if leads:
                print(f"  ✓ ASSOCIATED LEADS: {len(leads)}")
                for lead in leads:
                    print(f"    Lead ID: {lead.id}")
                    print(f"      Name: {lead.name}")
                    print(f"      Email: {lead.email}")
                    print(f"      Phone: {lead.phone}")
                    print(f"      Created: {lead.created_at}")
            else:
                print(f"  ✗ NO LEADS ASSOCIATED")
            
            print("-" * 80)
        
        # Check for any leads with "bob" in name or email
        print("\n" + "=" * 80)
        print("CHECKING FOR LEADS WITH 'bob' IN NAME OR EMAIL")
        print("=" * 80)
        
        bob_lead_stmt = select(Lead).where(
            Lead.tenant_id == 1,
            or_(
                Lead.name.ilike("%bob%"),
                Lead.email.ilike("%bob%")
            )
        ).order_by(desc(Lead.created_at))
        
        bob_result = await session.execute(bob_lead_stmt)
        bob_leads = bob_result.scalars().all()
        
        if bob_leads:
            print(f"\nFound {len(bob_leads)} lead(s) with 'bob':")
            for lead in bob_leads:
                print(f"  Lead ID: {lead.id}, Conversation ID: {lead.conversation_id}")
                print(f"    Name: {lead.name}, Email: {lead.email}")
                print(f"    Created: {lead.created_at}")
        else:
            print("\nNo leads found with 'bob' in name or email")
        
        # Check recent leads for tenant 1
        print("\n" + "=" * 80)
        print("RECENT LEADS FOR TENANT 1 (Last 2 hours)")
        print("=" * 80)
        
        recent_lead_stmt = select(Lead).where(
            Lead.tenant_id == 1,
            Lead.created_at >= cutoff
        ).order_by(desc(Lead.created_at))
        
        recent_lead_result = await session.execute(recent_lead_stmt)
        recent_leads = recent_lead_result.scalars().all()
        
        if recent_leads:
            print(f"\nFound {len(recent_leads)} recent lead(s):")
            for lead in recent_leads:
                print(f"  Lead ID: {lead.id}, Conversation ID: {lead.conversation_id}")
                print(f"    Name: {lead.name}, Email: {lead.email}, Phone: {lead.phone}")
                print(f"    Created: {lead.created_at}")
        else:
            print("\nNo recent leads found for tenant 1")

if __name__ == "__main__":
    asyncio.run(check_tenant1())

