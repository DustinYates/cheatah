"""Customers API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_tenant_context
from app.persistence.models.tenant import User
from app.persistence.repositories.customer_repository import CustomerRepository

router = APIRouter()


class CustomerResponse(BaseModel):
    """Customer response schema."""

    id: int
    tenant_id: int
    name: str | None
    email: str | None
    phone: str
    status: str
    account_type: str | None
    external_customer_id: str | None
    account_data: dict | None
    last_synced_at: str | None
    sync_source: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Customer list response with pagination."""

    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int


class CustomerCreateRequest(BaseModel):
    """Create customer request (for manual entry)."""

    name: str | None = None
    email: str | None = None
    phone: str
    status: str = "active"
    account_type: str | None = None
    external_customer_id: str | None = None
    account_data: dict | None = None


class CustomerUpdateRequest(BaseModel):
    """Update customer request."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    account_type: str | None = None
    account_data: dict | None = None


class CustomerStatsResponse(BaseModel):
    """Customer statistics response."""

    total: int
    active: int
    inactive: int
    suspended: int


def _serialize_customer(customer) -> dict:
    """Serialize customer to response dict."""
    return {
        "id": customer.id,
        "tenant_id": customer.tenant_id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "status": customer.status,
        "account_type": customer.account_type,
        "external_customer_id": customer.external_customer_id,
        "account_data": customer.account_data,
        "last_synced_at": customer.last_synced_at.isoformat() if customer.last_synced_at else None,
        "sync_source": customer.sync_source,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search by name, email, or phone"),
) -> CustomerListResponse:
    """List customers for a tenant."""
    repo = CustomerRepository(db)
    skip = (page - 1) * page_size

    if search:
        # Use search method
        customers = await repo.search(tenant_id, search, limit=page_size)
        total = len(customers)
    elif status:
        # Filter by status
        customers = await repo.list_by_status(tenant_id, status, skip=skip, limit=page_size)
        total = await repo.get_count(tenant_id, status=status)
    else:
        # List all
        customers = await repo.list(tenant_id, skip=skip, limit=page_size)
        total = await repo.get_count(tenant_id)

    return CustomerListResponse(
        items=[CustomerResponse(**_serialize_customer(c)) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=CustomerStatsResponse)
async def get_customer_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerStatsResponse:
    """Get customer statistics for a tenant."""
    repo = CustomerRepository(db)

    total = await repo.get_count(tenant_id)
    active = await repo.get_count(tenant_id, status="active")
    inactive = await repo.get_count(tenant_id, status="inactive")
    suspended = await repo.get_count(tenant_id, status="suspended")

    return CustomerStatsResponse(
        total=total,
        active=active,
        inactive=inactive,
        suspended=suspended,
    )


@router.get("/search")
async def search_customers(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=50),
) -> list[CustomerResponse]:
    """Search customers by name, email, or phone."""
    repo = CustomerRepository(db)
    customers = await repo.search(tenant_id, q, limit=limit)
    return [CustomerResponse(**_serialize_customer(c)) for c in customers]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerResponse:
    """Get a single customer by ID."""
    repo = CustomerRepository(db)
    customer = await repo.get_by_id(tenant_id, customer_id)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse(**_serialize_customer(customer))


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: CustomerCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerResponse:
    """Create a new customer (manual entry)."""
    repo = CustomerRepository(db)

    # Check if phone already exists
    existing = await repo.get_by_phone(tenant_id, request.phone)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this phone number already exists",
        )

    customer = await repo.create(
        tenant_id=tenant_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        status=request.status,
        account_type=request.account_type,
        external_customer_id=request.external_customer_id,
        account_data=request.account_data,
        sync_source="manual",
    )

    return CustomerResponse(**_serialize_customer(customer))


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    request: CustomerUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> CustomerResponse:
    """Update a customer."""
    repo = CustomerRepository(db)

    # Build update dict excluding None values
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    customer = await repo.update(tenant_id, customer_id, **update_data)

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse(**_serialize_customer(customer))


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete a customer."""
    repo = CustomerRepository(db)
    deleted = await repo.delete(tenant_id, customer_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
