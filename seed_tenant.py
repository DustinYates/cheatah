import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.persistence.models.tenant import Tenant

async def create_tenant():
    database_url = os.environ.get("DATABASE_URL")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Tenant).where(Tenant.id == 1))
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"Tenant already exists: {existing.name}")
            return
        
        tenant = Tenant(
            name="Demo Company",
            subdomain="demo",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        print(f"Created tenant: {tenant.name} (ID: {tenant.id})")

asyncio.run(create_tenant())
