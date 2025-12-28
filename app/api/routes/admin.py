"""Admin routes for global admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.api.schemas.tenant import AdminTenantResponse, AdminTenantUpdate, TenantCreate
from app.persistence.database import get_db
from app.persistence.models.tenant import Tenant, User
from app.persistence.repositories.tenant_repository import TenantRepository

router = APIRouter()


@router.post("/tenants", response_model=AdminTenantResponse)
async def create_tenant(
    tenant_data: TenantCreate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Create a new tenant."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.create(
        None,  # No tenant_id for tenant creation
        name=tenant_data.name,
        subdomain=tenant_data.subdomain,
        is_active=tenant_data.is_active,
    )
    return AdminTenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        end_date=tenant.end_date.isoformat() if tenant.end_date else None,
        tier=tenant.tier,
    )


@router.get("/tenants", response_model=list[AdminTenantResponse])
async def list_tenants(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> list[AdminTenantResponse]:
    """List all tenants."""
    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.list_all(skip=skip, limit=limit)
    return [
        AdminTenantResponse(
            id=t.id,
            name=t.name,
            subdomain=t.subdomain,
            is_active=t.is_active,
            created_at=t.created_at.isoformat(),
            end_date=t.end_date.isoformat() if t.end_date else None,
            tier=t.tier,
        )
        for t in tenants
    ]


@router.get("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def get_tenant(
    tenant_id: int,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Get a tenant by ID."""
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return AdminTenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        end_date=tenant.end_date.isoformat() if tenant.end_date else None,
        tier=tenant.tier,
    )


@router.put("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_update: AdminTenantUpdate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Update tenant admin-only fields."""
    tenant_repo = TenantRepository(db)
    update_data = {}
    fields_set = tenant_update.model_fields_set
    if "end_date" in fields_set:
        update_data["end_date"] = tenant_update.end_date
    if "tier" in fields_set:
        update_data["tier"] = tenant_update.tier

    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return AdminTenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        end_date=tenant.end_date.isoformat() if tenant.end_date else None,
        tier=tenant.tier,
    )
