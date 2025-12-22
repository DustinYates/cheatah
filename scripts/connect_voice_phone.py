"""Connect existing Twilio phone number to voice system."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.infrastructure.twilio_client import TwilioVoiceClient
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant import TenantBusinessProfile
from app.settings import settings
from sqlalchemy import select

# Load from environment or settings
import os
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or settings.twilio_account_sid
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or settings.twilio_auth_token
PHONE_NUMBER = os.getenv("TWILIO_VOICE_PHONE", "+18333615689")  # Your Twilio voice number
TENANT_ID = int(os.getenv("TENANT_ID", "1"))

# Your webhook base URL
WEBHOOK_BASE = os.getenv("TWILIO_WEBHOOK_URL_BASE") or settings.twilio_webhook_url_base or "https://your-domain.com"


async def connect_voice_phone():
    """Connect existing Twilio phone number to voice system."""
    print("Connecting Twilio Voice Phone Number")
    print("=" * 50)
    
    # Initialize Twilio client with your credentials
    voice_client = TwilioVoiceClient(
        account_sid=TWILIO_ACCOUNT_SID,
        auth_token=TWILIO_AUTH_TOKEN,
    )
    print(f"✓ Twilio client initialized")
    
    # Find the phone number SID by listing all numbers
    print(f"\nFinding phone number SID for {PHONE_NUMBER}...")
    try:
        # List all phone numbers
        phone_numbers = voice_client.client.incoming_phone_numbers.list()
        
        phone_number_sid = None
        for number in phone_numbers:
            print(f"  Found: {number.phone_number} (SID: {number.sid})")
            if number.phone_number == PHONE_NUMBER:
                phone_number_sid = number.sid
                print(f"✓ Matched phone number SID: {phone_number_sid}")
                break
        
        if not phone_number_sid:
            print(f"✗ Phone number {PHONE_NUMBER} not found in your Twilio account")
            print("  Available numbers listed above")
            return
            
    except Exception as e:
        print(f"✗ Error finding phone number: {e}")
        return
    
    # Configure webhook URLs
    voice_url = f"{WEBHOOK_BASE}/api/v1/voice/inbound"
    status_callback_url = f"{WEBHOOK_BASE}/api/v1/voice/status"
    
    print(f"\nConfiguring webhooks...")
    print(f"  Voice URL: {voice_url}")
    print(f"  Status Callback: {status_callback_url}")
    
    try:
        result = voice_client.configure_phone_webhook(
            phone_number_sid=phone_number_sid,
            voice_url=voice_url,
            status_callback_url=status_callback_url,
        )
        print(f"✓ Webhooks configured successfully")
        print(f"  Updated Voice URL: {result.get('voice_url')}")
        print(f"  Updated Status Callback: {result.get('status_callback')}")
    except Exception as e:
        print(f"✗ Error configuring webhooks: {e}")
        return
    
    # Store phone number in database
    print(f"\nStoring phone number in database...")
    async with AsyncSessionLocal() as db:
        # Get or create tenant business profile
        stmt = select(TenantBusinessProfile).where(
            TenantBusinessProfile.tenant_id == TENANT_ID
        )
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        
        if not profile:
            profile = TenantBusinessProfile(tenant_id=TENANT_ID)
            db.add(profile)
            print(f"✓ Created new business profile for tenant {TENANT_ID}")
        else:
            print(f"✓ Found existing business profile for tenant {TENANT_ID}")
        
        profile.twilio_voice_phone = PHONE_NUMBER
        await db.commit()
        print(f"✓ Phone number stored in database: {PHONE_NUMBER}")
    
    print("\n" + "=" * 50)
    print("✓ Voice phone number connected successfully!")
    print(f"\nYour phone number {PHONE_NUMBER} is now configured to:")
    print(f"  - Receive calls at: {voice_url}")
    print(f"  - Send status updates to: {status_callback_url}")
    print(f"\nMake a test call to {PHONE_NUMBER} to verify it works!")


if __name__ == "__main__":
    asyncio.run(connect_voice_phone())

