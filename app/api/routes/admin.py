"""Admin routes for global admin operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_global_admin
from app.api.schemas.tenant import (
    AdminTenantResponse,
    AdminTenantUpdate,
    TenantCreate,
    TenantOverviewStats,
    TenantsOverviewResponse,
)
from app.persistence.database import get_db
from app.persistence.models.contact import Contact
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead
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


@router.get("/tenants/overview", response_model=TenantsOverviewResponse)
async def get_tenants_overview(
    current_user: Annotated[User, Depends(require_global_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantsOverviewResponse:
    """Get high-level overview stats for all tenants (master admin only)."""
    tenant_repo = TenantRepository(db)
    tenants = await tenant_repo.list_all(skip=0, limit=1000)

    # Get stats for each tenant in efficient batch queries
    tenant_ids = [t.id for t in tenants]

    # Query conversation counts per tenant
    conv_counts_query = (
        select(Conversation.tenant_id, func.count(Conversation.id))
        .where(Conversation.tenant_id.in_(tenant_ids))
        .group_by(Conversation.tenant_id)
    )
    conv_result = await db.execute(conv_counts_query)
    conv_counts = {row[0]: row[1] for row in conv_result}

    # Query lead counts per tenant
    lead_counts_query = (
        select(Lead.tenant_id, func.count(Lead.id))
        .where(Lead.tenant_id.in_(tenant_ids))
        .group_by(Lead.tenant_id)
    )
    lead_result = await db.execute(lead_counts_query)
    lead_counts = {row[0]: row[1] for row in lead_result}

    # Query contact counts per tenant (excluding deleted)
    contact_counts_query = (
        select(Contact.tenant_id, func.count(Contact.id))
        .where(Contact.tenant_id.in_(tenant_ids))
        .where(Contact.deleted_at.is_(None))
        .group_by(Contact.tenant_id)
    )
    contact_result = await db.execute(contact_counts_query)
    contact_counts = {row[0]: row[1] for row in contact_result}

    # Query last activity (most recent message) per tenant
    last_activity_query = (
        select(Conversation.tenant_id, func.max(Message.created_at))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id.in_(tenant_ids))
        .group_by(Conversation.tenant_id)
    )
    activity_result = await db.execute(last_activity_query)
    last_activities = {row[0]: row[1].isoformat() if row[1] else None for row in activity_result}

    # Build response
    tenant_stats = []
    active_count = 0
    for tenant in tenants:
        if tenant.is_active:
            active_count += 1
        tenant_stats.append(
            TenantOverviewStats(
                id=tenant.id,
                name=tenant.name,
                subdomain=tenant.subdomain,
                is_active=tenant.is_active,
                tier=tenant.tier,
                total_conversations=conv_counts.get(tenant.id, 0),
                total_leads=lead_counts.get(tenant.id, 0),
                total_contacts=contact_counts.get(tenant.id, 0),
                last_activity=last_activities.get(tenant.id),
            )
        )

    # Sort by last activity (most recent first), then by name
    tenant_stats.sort(
        key=lambda t: (t.last_activity or "", t.name),
        reverse=True,
    )

    return TenantsOverviewResponse(
        tenants=tenant_stats,
        total_tenants=len(tenants),
        active_tenants=active_count,
    )
