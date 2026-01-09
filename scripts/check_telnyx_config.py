"""Check Telnyx configuration for tenant 3."""
import asyncio
import os
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Getting from GCP secrets...")
        import subprocess
        result = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest", 
             "--secret=DATABASE_URL", "--project=chattercheetah"],
            capture_output=True, text=True
        )
        db_url = result.stdout.strip()
    
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check tenant 3 SMS config
        result = await session.execute(text("""
            SELECT t.id, t.name, tsc.telnyx_phone_number, tsc.telnyx_connection_id,
                   tsc.voice_enabled, tsc.sms_enabled, tsc.telnyx_messaging_profile_id
            FROM tenants t
            JOIN tenant_sms_configs tsc ON t.id = tsc.tenant_id
            WHERE t.id = 3
        """))
        row = result.fetchone()
        if row:
            print(f"Tenant ID: {row[0]}")
            print(f"Name: {row[1]}")
            print(f"Telnyx Phone: {row[2]}")
            print(f"Telnyx Connection ID: {row[3]}")
            print(f"Voice Enabled: {row[4]}")
            print(f"SMS Enabled: {row[5]}")
            print(f"Messaging Profile ID: {row[6]}")
        else:
            print("Tenant 3 not found!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
