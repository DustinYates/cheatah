"""Script to sync customers from Jackrabbit API to the customers table.

Usage:
    uv run python scripts/sync_jackrabbit_customers.py --tenant-id 3

This script pulls customer data directly from the Jackrabbit Families API
and syncs it to the customers table for the Customer Support feature.
"""

import asyncio
import argparse
import logging
from datetime import datetime

import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Jackrabbit REST API endpoints
JACKRABBIT_BASE_URL = "https://app.jackrabbitclass.com/jr3.0/families"


async def fetch_families_from_jackrabbit(api_key_1: str, api_key_2: str, limit: int = 100) -> list[dict]:
    """Fetch family/customer data from Jackrabbit Families API.

    Args:
        api_key_1: Jackrabbit API Key 1
        api_key_2: Jackrabbit API Key 2
        limit: Maximum families to fetch

    Returns:
        List of family records
    """
    headers = {
        "Authorization": f"Basic {api_key_1}:{api_key_2}",
    }

    params = {
        "rows": limit,
    }

    logger.info(f"Fetching up to {limit} families from Jackrabbit...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(JACKRABBIT_BASE_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            families = data if isinstance(data, list) else data.get("families", data.get("rows", []))
            logger.info(f"Fetched {len(families)} families from Jackrabbit")
            return families

        except httpx.HTTPStatusError as e:
            logger.error(f"Jackrabbit API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch from Jackrabbit: {e}")
            raise


async def sync_families_to_customers(tenant_id: int, families: list[dict]) -> tuple[int, int]:
    """Sync Jackrabbit families to the customers table.

    Args:
        tenant_id: Tenant ID
        families: List of family records from Jackrabbit

    Returns:
        Tuple of (created_count, updated_count)
    """
    from app.persistence.database import AsyncSessionLocal
    from app.persistence.repositories.customer_repository import CustomerRepository
    from app.core.phone import normalize_phone

    created = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        repo = CustomerRepository(session)

        for family in families:
            try:
                # Extract customer data from Jackrabbit family record
                jackrabbit_id = str(family.get("id") or family.get("family_id") or family.get("fam_id", ""))
                if not jackrabbit_id:
                    logger.warning(f"Skipping family with no ID: {family}")
                    continue

                # Try multiple phone field names
                phone = (
                    family.get("phone") or
                    family.get("phone1") or
                    family.get("home_phone") or
                    family.get("cell_phone") or
                    family.get("mobile") or
                    ""
                )

                if not phone:
                    logger.debug(f"Skipping family {jackrabbit_id} - no phone")
                    continue

                # Normalize phone
                try:
                    phone = normalize_phone(phone)
                except:
                    # Basic normalization if phone module fails
                    phone = "".join(c for c in phone if c.isdigit() or c == "+")
                    if len(phone) == 10:
                        phone = "+1" + phone
                    elif len(phone) == 11 and phone.startswith("1"):
                        phone = "+" + phone
                    elif not phone.startswith("+"):
                        phone = "+" + phone

                # Extract name
                name = (
                    family.get("name") or
                    family.get("family_name") or
                    f"{family.get('first_name', '')} {family.get('last_name', '')}".strip() or
                    None
                )

                email = family.get("email") or family.get("email1")

                # Build account_data with available fields
                account_data = {
                    k: v for k, v in family.items()
                    if k not in ["id", "family_id", "fam_id", "phone", "phone1", "home_phone",
                                 "cell_phone", "mobile", "email", "email1", "name", "family_name",
                                 "first_name", "last_name"]
                    and v is not None
                }

                # Check if customer exists
                existing = await repo.get_by_external_id(tenant_id, jackrabbit_id)

                if existing:
                    # Update existing
                    await repo.update(tenant_id, existing.id,
                        name=name,
                        email=email,
                        phone=phone,
                        account_data=account_data,
                        last_synced_at=datetime.utcnow(),
                        sync_source="jackrabbit"
                    )
                    updated += 1
                    logger.debug(f"Updated customer {jackrabbit_id}: {name}")
                else:
                    # Create new
                    await repo.create(
                        tenant_id=tenant_id,
                        external_customer_id=jackrabbit_id,
                        phone=phone,
                        name=name,
                        email=email,
                        status="active",
                        account_data=account_data,
                        last_synced_at=datetime.utcnow(),
                        sync_source="jackrabbit"
                    )
                    created += 1
                    logger.debug(f"Created customer {jackrabbit_id}: {name}")

            except Exception as e:
                logger.error(f"Failed to sync family {family.get('id')}: {e}")
                continue

    return created, updated


async def get_jackrabbit_credentials(tenant_id: int) -> tuple[str, str]:
    """Get decrypted Jackrabbit API keys for a tenant."""
    from app.persistence.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig

    async with AsyncSessionLocal() as session:
        stmt = select(TenantCustomerServiceConfig).where(
            TenantCustomerServiceConfig.tenant_id == tenant_id
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise ValueError(f"No customer service config found for tenant {tenant_id}")

        if not config.jackrabbit_api_key_1 or not config.jackrabbit_api_key_2:
            raise ValueError(f"Jackrabbit API keys not configured for tenant {tenant_id}")

        return config.jackrabbit_api_key_1, config.jackrabbit_api_key_2


async def main(tenant_id: int, limit: int = 100, dry_run: bool = False):
    """Main sync function."""
    logger.info(f"Starting Jackrabbit customer sync for tenant {tenant_id}")

    # Get credentials
    try:
        api_key_1, api_key_2 = await get_jackrabbit_credentials(tenant_id)
        logger.info("Retrieved Jackrabbit credentials")
    except ValueError as e:
        logger.error(str(e))
        return

    # Fetch families from Jackrabbit
    try:
        families = await fetch_families_from_jackrabbit(api_key_1, api_key_2, limit=limit)
    except Exception as e:
        logger.error(f"Failed to fetch families: {e}")
        return

    if not families:
        logger.warning("No families returned from Jackrabbit API")
        return

    logger.info(f"Sample family record: {families[0] if families else 'none'}")

    if dry_run:
        logger.info(f"DRY RUN: Would sync {len(families)} families")
        return

    # Sync to customers table
    created, updated = await sync_families_to_customers(tenant_id, families)

    logger.info(f"Sync complete: {created} created, {updated} updated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Jackrabbit customers to database")
    parser.add_argument("--tenant-id", type=int, required=True, help="Tenant ID to sync")
    parser.add_argument("--limit", type=int, default=100, help="Max families to fetch")
    parser.add_argument("--dry-run", action="store_true", help="Just fetch and show, don't sync")

    args = parser.parse_args()
    asyncio.run(main(args.tenant_id, args.limit, args.dry_run))
