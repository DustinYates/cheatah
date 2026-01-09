"""List all tenants and their telephony configurations."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.persistence.database import AsyncSessionLocal
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant import Tenant


async def list_all():
    """List all tenants and their voice configurations."""
    print("=" * 80)
    print("ALL TENANTS AND TELEPHONY CONFIGURATIONS")
    print("=" * 80)
    print()

    async with AsyncSessionLocal() as db:
        # Get all tenants
        tenants_stmt = select(Tenant).order_by(Tenant.id)
        tenants_result = await db.execute(tenants_stmt)
        tenants = tenants_result.scalars().all()

        # Get all telephony configs
        configs_stmt = select(TenantSmsConfig)
        configs_result = await db.execute(configs_stmt)
        configs = {c.tenant_id: c for c in configs_result.scalars().all()}

        print(f"{'ID':<4} {'Name':<30} {'Subdomain':<20} {'Active':<8} {'Voice':<8} {'Provider':<10} {'Voice Phone':<15}")
        print("-" * 110)

        for tenant in tenants:
            config = configs.get(tenant.id)
            voice_enabled = config.voice_enabled if config else False
            provider = config.provider if config else "N/A"
            voice_phone = (config.voice_phone_number if config else None) or "N/A"

            print(f"{tenant.id:<4} {tenant.name[:28]:<30} {tenant.subdomain[:18]:<20} {str(tenant.is_active):<8} {str(voice_enabled):<8} {provider:<10} {voice_phone:<15}")

        print()
        print(f"Total tenants: {len(tenants)}")
        print(f"Total telephony configs: {len(configs)}")


if __name__ == "__main__":
    asyncio.run(list_all())
