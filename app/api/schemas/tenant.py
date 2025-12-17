"""Tenant-related schemas."""

from pydantic import BaseModel


class TenantCreate(BaseModel):
    """Tenant creation request."""

    name: str
    subdomain: str
    is_active: bool = True


class TenantUpdate(BaseModel):
    """Tenant update request."""

    name: str | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    """Tenant response."""

    id: int
    name: str
    subdomain: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True
