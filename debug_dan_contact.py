#!/usr/bin/env python
"""Debug script to check dan contact and associated data."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.persistence.database import AsyncSessionLocal
from sqlalchemy import select, or_
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead
from app.persistence.models.contact import Contact
from app.persistence.models.tenant import Tenant

async def debug_dan():
    """Debug the dan contact."""
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("ALL TENANTS")
        print("=" * 80)
        tenant_stmt = select(Tenant)
        tenant_result = await session.execute(tenant_stmt)
        tenants = tenant_result.scalars().all()
        for t in tenants:
            print(f"  Tenant ID: {t.id}, Name: {t.name}, Subdomain: {t.subdomain}")
        
        print("\n" + "=" * 80)
        print("ALL CONTACTS (first 20)")
        print("=" * 80)
        all_contacts_stmt = select(Contact).limit(20)
        all_contacts_result = await session.execute(all_contacts_stmt)
        all_contacts = all_contacts_result.scalars().all()
        for c in all_contacts:
            print(f"  ID: {c.id}, tenant: {c.tenant_id}, name: {c.name}, email: {c.email}, phone: {c.phone}, lead_id: {c.lead_id}")
        
        print("\n" + "=" * 80)
        print("DEBUGGING DAN CONTACT")
        print("=" * 80)
        
        # Find contacts matching dan
        contact_stmt = select(Contact).where(
            or_(
                Contact.name.ilike('%dan%'),
                Contact.email.ilike('%danny%')
            )
        )
        result = await session.execute(contact_stmt)
        contacts = result.scalars().all()
        
        print(f"\nFound {len(contacts)} contacts matching 'dan':")
        for c in contacts:
            print(f"\n  Contact ID: {c.id}")
            print(f"    tenant_id: {c.tenant_id}")
            print(f"    lead_id: {c.lead_id}")
            print(f"    name: {c.name}")
            print(f"    email: {c.email}")
            print(f"    phone: {c.phone}")
            print(f"    source: {c.source}")
            
            # Check linked lead
            if c.lead_id:
                lead_stmt = select(Lead).where(Lead.id == c.lead_id)
                lead_result = await session.execute(lead_stmt)
                lead = lead_result.scalar_one_or_none()
                if lead:
                    print(f"\n    Linked Lead (id={lead.id}):")
                    print(f"      conversation_id: {lead.conversation_id}")
                    print(f"      email: {lead.email}")
                    print(f"      phone: {lead.phone}")
                    print(f"      status: {lead.status}")
                else:
                    print(f"\n    WARNING: lead_id={c.lead_id} but lead not found!")
            else:
                print(f"\n    No lead_id linked")
            
            # Find leads with matching email/phone
            email = c.email
            phone = c.phone
            if email or phone:
                conditions = []
                if email:
                    conditions.append(Lead.email == email)
                if phone:
                    conditions.append(Lead.phone == phone)
                
                matching_leads_stmt = select(Lead).where(
                    Lead.tenant_id == c.tenant_id,
                    Lead.conversation_id.isnot(None),
                    or_(*conditions)
                )
                matching_result = await session.execute(matching_leads_stmt)
                matching_leads = matching_result.scalars().all()
                
                print(f"\n    Leads with matching email/phone AND conversation_id:")
                if matching_leads:
                    for ml in matching_leads:
                        print(f"      Lead ID: {ml.id}, conv_id: {ml.conversation_id}, email: {ml.email}, phone: {ml.phone}")
                else:
                    print(f"      None found")
            
            # Check for any conversations by phone (SMS)
            if phone:
                sms_stmt = select(Conversation).where(
                    Conversation.tenant_id == c.tenant_id,
                    Conversation.phone_number == phone,
                    Conversation.channel == 'sms'
                )
                sms_result = await session.execute(sms_stmt)
                sms_convs = sms_result.scalars().all()
                print(f"\n    SMS Conversations with phone={phone}:")
                if sms_convs:
                    for sc in sms_convs:
                        print(f"      Conv ID: {sc.id}, channel: {sc.channel}")
                else:
                    print(f"      None found")
            
            # Show all leads for this tenant
            print(f"\n    All leads for tenant_id={c.tenant_id}:")
            all_leads_stmt = select(Lead).where(Lead.tenant_id == c.tenant_id).limit(10)
            all_leads_result = await session.execute(all_leads_stmt)
            all_leads = all_leads_result.scalars().all()
            for al in all_leads:
                print(f"      Lead ID: {al.id}, conv_id: {al.conversation_id}, email: {al.email}, phone: {al.phone}, status: {al.status}")

if __name__ == "__main__":
    asyncio.run(debug_dan())

