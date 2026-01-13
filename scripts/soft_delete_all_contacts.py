"""Soft delete all contacts from all tenants."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from sqlalchemy import update, select, func
from app.persistence.database import async_session_factory
from app.persistence.models.contact import Contact


async def soft_delete_all_contacts():
    """Soft delete all contacts from all tenants."""
    async with async_session_factory() as session:
        # Count contacts before
        count_stmt = select(func.count()).select_from(Contact).where(Contact.deleted_at.is_(None))
        result = await session.execute(count_stmt)
        count_before = result.scalar()

        print(f"Found {count_before} active contacts to soft delete...")

        if count_before == 0:
            print("No contacts to delete.")
            return

        # Soft delete all contacts that aren't already deleted
        stmt = (
            update(Contact)
            .where(Contact.deleted_at.is_(None))
            .values(deleted_at=datetime.utcnow())
        )

        result = await session.execute(stmt)
        await session.commit()

        print(f"Soft deleted {result.rowcount} contacts from all tenants.")


if __name__ == "__main__":
    asyncio.run(soft_delete_all_contacts())
