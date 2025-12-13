"""Admin routes for global admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.api.schemas.tenant import TenantCreate, TenantResponse
from app.persistence.database import get_db
from app.persistence.models.tenant import Tenant, User
from app.persistence.repositories.tenant_repository import TenantRepository

router = APIRouter()


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Create a new tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.create(
        None,  # No tenant_id for tenant creation
        name=tenant_data.name,
        subdomain=tenant_data.subdomain,
        is_active=tenant_data.is_active,
    )
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
    )


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> list[TenantResponse]:
    """List all tenants."""
    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.list_all(skip=skip, limit=limit)
    return [
        TenantResponse(
            id=t.id,
            name=t.name,
            subdomain=t.subdomain,
            is_active=t.is_active,
            created_at=t.created_at.isoformat(),
        )
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Get a tenant by ID."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
    )

