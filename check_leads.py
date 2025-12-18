#!/usr/bin/env python
"""Debug script to check for recent leads in the database."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, desc, func
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import Tenant

async def check_recent_leads():
    """Check for recent leads in the database."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("CHECKING FOR RECENT LEADS")
        print("=" * 80)
        
        # Get leads from last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stmt = select(Lead).where(
            Lead.created_at >= cutoff
        ).order_by(desc(Lead.created_at))
        
        result = await session.execute(stmt)
        leads = result.scalars().all()
        
        print(f"\nFound {len(leads)} leads in the last 24 hours:\n")
        
        if not leads:
            print("No recent leads found.")
            print("\nChecking all leads...")
            all_stmt = select(Lead).order_by(desc(Lead.created_at)).limit(10)
            all_result = await session.execute(all_stmt)
            all_leads = all_result.scalars().all()
            print(f"Found {len(all_leads)} total leads (showing last 10):\n")
            leads = all_leads
        
        for lead in leads:
            print(f"Lead ID: {lead.id}")
            print(f"  Tenant ID: {lead.tenant_id}")
            print(f"  Conversation ID: {lead.conversation_id}")
            print(f"  Name: {lead.name}")
            print(f"  Email: {lead.email}")
            print(f"  Phone: {lead.phone}")
            print(f"  Status: {lead.status}")
            print(f"  Created: {lead.created_at}")
            print("-" * 80)
        
        # Check for specific test email
        print("\n" + "=" * 80)
        print("CHECKING FOR SPECIFIC TEST EMAIL (bob@bob.com)")
        print("=" * 80)
        
        email_stmt = select(Lead).where(Lead.email == "bob@bob.com")
        email_result = await session.execute(email_stmt)
        email_leads = email_result.scalars().all()
        
        if email_leads:
            print(f"\nFound {len(email_leads)} lead(s) with email bob@bob.com:")
            for lead in email_leads:
                print(f"  Lead ID: {lead.id}, Tenant: {lead.tenant_id}, "
                      f"Created: {lead.created_at}")
        else:
            print("\nNo leads found with email bob@bob.com")
        
        # Check tenants
        print("\n" + "=" * 80)
        print("LISTING ALL TENANTS")
        print("=" * 80)
        tenant_stmt = select(Tenant).order_by(Tenant.id)
        tenant_result = await session.execute(tenant_stmt)
        tenants = tenant_result.scalars().all()
        
        print(f"\nFound {len(tenants)} tenants:")
        for tenant in tenants:
            print(f"  Tenant ID: {tenant.id}, Name: {tenant.name}, "
                  f"Subdomain: {tenant.subdomain}, Active: {tenant.is_active}")

if __name__ == "__main__":
    asyncio.run(check_recent_leads())

