"""Tenant routes for tenant operations."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_tenant, get_current_user
from app.persistence.database import get_db
from app.persistence.models.tenant import Tenant, User
from app.persistence.repositories.tenant_repository import TenantRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class TenantResponse(BaseModel):
    """Tenant response."""

    id: int
    name: str
    subdomain: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class TenantUpdate(BaseModel):
    """Tenant update request."""

    name: str | None = None
    is_active: bool | None = None


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant_info(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Get current tenant information."""
    if tenant_id is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant associated with user",
        )
    
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        from fastapi import HTTPException, status
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


@router.put("/me", response_model=TenantResponse)
async def update_current_tenant(
    tenant_update: TenantUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Update current tenant."""
    if tenant_id is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant associated with user",
        )
    
    tenant_repo = TenantRepository(db)
    update_data = {}
    if tenant_update.name is not None:
        update_data["name"] = tenant_update.name
    if tenant_update.is_active is not None:
        update_data["is_active"] = tenant_update.is_active
    
    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        from fastapi import HTTPException, status
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

