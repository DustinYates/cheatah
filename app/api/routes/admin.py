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


def _tenant_to_response(tenant: Tenant) -> AdminTenantResponse:
    """Convert a Tenant model to AdminTenantResponse."""
    return AdminTenantResponse(
        id=tenant.id,
        tenant_number=tenant.tenant_number,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
        end_date=tenant.end_date.isoformat() if tenant.end_date else None,
        tier=tenant.tier,
    )


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
    return _tenant_to_response(tenant)


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
    return [_tenant_to_response(t) for t in tenants]


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
    return _tenant_to_response(tenant)


@router.put("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def update_tenant(
    tenant_id: int,
    tenant_update: AdminTenantUpdate,
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminTenantResponse:
    """Update tenant admin fields."""
    tenant_repo = TenantRepository(db)
    update_data = {}
    fields_set = tenant_update.model_fields_set
    if "tenant_number" in fields_set:
        update_data["tenant_number"] = tenant_update.tenant_number
    if "end_date" in fields_set:
        update_data["end_date"] = tenant_update.end_date
    if "tier" in fields_set:
        update_data["tier"] = tenant_update.tier
    if "name" in fields_set:
        update_data["name"] = tenant_update.name
    if "is_active" in fields_set:
        update_data["is_active"] = tenant_update.is_active

    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return _tenant_to_response(tenant)
