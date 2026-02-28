"""Connections API routes — unified view of Contacts + Customers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_tenant_context
from app.core.phone import normalize_phone_for_dedup
from app.persistence.models.contact import Contact
from app.persistence.models.customer import Customer
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import User
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.customer_repository import CustomerRepository

# Reuse enrichment helpers from contacts route
from app.api.routes.contacts import (
    _get_customer_names_by_phone,
    _get_contact_communication_timestamps,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ConnectionResponse(BaseModel):
    """Unified connection response — contact, customer, or both."""

    id: int
    record_type: str  # "contact" | "customer" | "both"
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    created_at: str

    # Tags
    pipeline_stage: str | None = None
    customer_status: str | None = None
    has_interactions: bool = False

    # IDs for navigation
    contact_id: int | None = None
    customer_id: int | None = None
    lead_id: int | None = None

    # Contact fields
    tags: list[str] | None = None
    location: str | None = None
    company: str | None = None
    role: str | None = None
    notes: str | None = None
    merged_into_contact_id: int | None = None

    # Customer fields
    customer_name: str | None = None
    account_type: str | None = None
    external_customer_id: str | None = None
    last_synced_at: str | None = None

    # Timestamps
    first_contacted: str | None = None
    last_contacted: str | None = None

    class Config:
        from_attributes = True


class ConnectionListResponse(BaseModel):
    """Paginated connection list."""

    items: list[ConnectionResponse]
    total: int
    page: int
    page_size: int


class ConnectionStatsResponse(BaseModel):
    """Connection stats."""

    total: int
    contacts_only: int
    customers_only: int
    linked: int
    by_pipeline_stage: dict[str, int]
    by_customer_status: dict[str, int]
    with_interactions: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_connection_from_contact(
    contact: Contact,
    customer: Customer | None,
    pipeline_stage: str | None,
    first_contacted: str | None,
    last_contacted: str | None,
) -> ConnectionResponse:
    """Build a ConnectionResponse from a Contact (optionally matched to a Customer)."""
    has_interactions = first_contacted is not None or last_contacted is not None
    return ConnectionResponse(
        id=contact.id,
        record_type="both" if customer else "contact",
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        source=contact.source,
        created_at=contact.created_at.isoformat() if contact.created_at else "",
        pipeline_stage=pipeline_stage,
        customer_status=customer.status if customer else None,
        has_interactions=has_interactions,
        contact_id=contact.id,
        customer_id=customer.id if customer else None,
        lead_id=contact.lead_id,
        tags=contact.tags or [],
        location=contact.location,
        company=contact.company,
        role=contact.role,
        notes=contact.notes,
        merged_into_contact_id=contact.merged_into_contact_id,
        customer_name=customer.name if customer else None,
        account_type=customer.account_type if customer else None,
        external_customer_id=customer.external_customer_id if customer else None,
        last_synced_at=customer.last_synced_at.isoformat() if customer and customer.last_synced_at else None,
        first_contacted=first_contacted,
        last_contacted=last_contacted,
    )


def _build_connection_from_customer(customer: Customer) -> ConnectionResponse:
    """Build a ConnectionResponse from a standalone Customer (no linked contact)."""
    return ConnectionResponse(
        id=customer.id,
        record_type="customer",
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        source="jackrabbit" if customer.sync_source == "jackrabbit" else "manual",
        created_at=customer.created_at.isoformat() if customer.created_at else "",
        pipeline_stage=None,
        customer_status=customer.status,
        has_interactions=False,
        contact_id=None,
        customer_id=customer.id,
        lead_id=None,
        tags=None,
        location=None,
        company=None,
        role=None,
        notes=None,
        merged_into_contact_id=None,
        customer_name=customer.name,
        account_type=customer.account_type,
        external_customer_id=customer.external_customer_id,
        last_synced_at=customer.last_synced_at.isoformat() if customer.last_synced_at else None,
        first_contacted=None,
        last_contacted=None,
    )


def _matches_search(conn: ConnectionResponse, query: str) -> bool:
    """Check if a connection matches a search query."""
    q = query.lower()
    return (
        (conn.name and q in conn.name.lower())
        or (conn.email and q in conn.email.lower())
        or (conn.phone and q in conn.phone.lower())
        or (conn.customer_name and q in conn.customer_name.lower())
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ConnectionListResponse)
async def list_connections(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=10000),
    search: str | None = Query(None),
    record_type: str | None = Query(None, description="contact, customer, or both"),
    pipeline_stage: str | None = Query(None),
    customer_status: str | None = Query(None),
    sort_by: str = Query("created_at", description="created_at, name, last_contacted"),
    sort_dir: str = Query("desc", description="asc or desc"),
) -> ConnectionListResponse:
    """List all connections (contacts + standalone customers) for the tenant."""

    contact_repo = ContactRepository(db)
    customer_repo = CustomerRepository(db)

    # ---- Step 1: Fetch all contacts (active, non-merged) ----
    contacts = await contact_repo.list_by_tenant(
        tenant_id=tenant_id,
        skip=0,
        limit=10000,
    )

    # ---- Step 2: Fetch all customers ----
    all_customers = await customer_repo.list(tenant_id, skip=0, limit=10000)

    # ---- Step 3: Build customer lookup maps ----
    # By contact_id FK (direct link)
    customer_by_contact_id: dict[int, Customer] = {}
    # By normalized phone (fallback matching)
    customer_by_norm_phone: dict[str, Customer] = {}

    for cust in all_customers:
        if cust.contact_id:
            customer_by_contact_id[cust.contact_id] = cust
        if cust.phone:
            norm = normalize_phone_for_dedup(cust.phone)
            customer_by_norm_phone[norm] = cust

    # ---- Step 4: Enrich contacts with timestamps and pipeline stages ----
    contact_ids = [c.id for c in contacts]
    timestamps_map: dict[int, tuple[str | None, str | None]] = {}
    stage_map: dict[int, str] = {}

    if contact_ids:
        timestamps_map = await _get_contact_communication_timestamps(db, contact_ids, tenant_id)

        lead_ids = [c.lead_id for c in contacts if c.lead_id]
        if lead_ids:
            lead_stages_result = await db.execute(
                select(Lead.id, Lead.pipeline_stage).where(Lead.id.in_(lead_ids))
            )
            stage_map = {row.id: row.pipeline_stage for row in lead_stages_result}

    # ---- Step 5: Build connection list from contacts ----
    connections: list[ConnectionResponse] = []
    matched_customer_ids: set[int] = set()

    for contact in contacts:
        # Find matching customer: first by contact_id FK, then by phone
        customer = customer_by_contact_id.get(contact.id)
        if not customer and contact.phone:
            norm = normalize_phone_for_dedup(contact.phone)
            customer = customer_by_norm_phone.get(norm)

        if customer:
            matched_customer_ids.add(customer.id)

        first_c, last_c = timestamps_map.get(contact.id, (None, None))
        p_stage = stage_map.get(contact.lead_id) if contact.lead_id else None

        connections.append(
            _build_connection_from_contact(contact, customer, p_stage, first_c, last_c)
        )

    # ---- Step 6: Append standalone customers (no linked contact) ----
    for cust in all_customers:
        if cust.id not in matched_customer_ids:
            connections.append(_build_connection_from_customer(cust))

    # ---- Step 7: Apply filters ----
    if search:
        connections = [c for c in connections if _matches_search(c, search)]

    if record_type:
        if record_type == "contact":
            connections = [c for c in connections if c.record_type == "contact"]
        elif record_type == "customer":
            connections = [c for c in connections if c.record_type == "customer"]
        elif record_type == "both":
            connections = [c for c in connections if c.record_type == "both"]

    if pipeline_stage:
        connections = [c for c in connections if c.pipeline_stage == pipeline_stage]

    if customer_status:
        connections = [c for c in connections if c.customer_status == customer_status]

    # ---- Step 8: Sort ----
    reverse = sort_dir == "desc"

    if sort_by == "name":
        connections.sort(key=lambda c: (c.name or c.customer_name or "").lower(), reverse=reverse)
    elif sort_by == "last_contacted":
        connections.sort(key=lambda c: c.last_contacted or "", reverse=reverse)
    else:  # created_at (default)
        connections.sort(key=lambda c: c.created_at or "", reverse=reverse)

    # ---- Step 9: Paginate ----
    total = len(connections)
    offset = (page - 1) * page_size
    paginated = connections[offset : offset + page_size]

    return ConnectionListResponse(
        items=paginated,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=ConnectionStatsResponse)
async def get_connection_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> ConnectionStatsResponse:
    """Get connection statistics for the tenant."""

    contact_repo = ContactRepository(db)
    customer_repo = CustomerRepository(db)

    # Get all contacts and customers
    contacts = await contact_repo.list_by_tenant(tenant_id=tenant_id, skip=0, limit=10000)
    all_customers = await customer_repo.list(tenant_id, skip=0, limit=10000)

    # Build customer match set (same logic as list_connections)
    customer_by_contact_id: dict[int, Customer] = {}
    customer_by_norm_phone: dict[str, Customer] = {}
    for cust in all_customers:
        if cust.contact_id:
            customer_by_contact_id[cust.contact_id] = cust
        if cust.phone:
            customer_by_norm_phone[normalize_phone_for_dedup(cust.phone)] = cust

    matched_customer_ids: set[int] = set()
    contacts_only = 0
    linked = 0

    for contact in contacts:
        customer = customer_by_contact_id.get(contact.id)
        if not customer and contact.phone:
            customer = customer_by_norm_phone.get(normalize_phone_for_dedup(contact.phone))
        if customer:
            matched_customer_ids.add(customer.id)
            linked += 1
        else:
            contacts_only += 1

    customers_only = sum(1 for c in all_customers if c.id not in matched_customer_ids)

    # Pipeline stage counts (from leads linked to contacts)
    lead_ids = [c.lead_id for c in contacts if c.lead_id]
    by_pipeline_stage: dict[str, int] = {}
    if lead_ids:
        result = await db.execute(
            select(Lead.pipeline_stage, func.count(Lead.id))
            .where(Lead.id.in_(lead_ids), Lead.pipeline_stage.isnot(None))
            .group_by(Lead.pipeline_stage)
        )
        by_pipeline_stage = {row[0]: row[1] for row in result}

    # Customer status counts
    by_customer_status: dict[str, int] = {}
    for cust in all_customers:
        status = cust.status or "unknown"
        by_customer_status[status] = by_customer_status.get(status, 0) + 1

    # Interaction count
    contact_ids = [c.id for c in contacts]
    timestamps_map = await _get_contact_communication_timestamps(db, contact_ids, tenant_id) if contact_ids else {}
    with_interactions = sum(1 for ts in timestamps_map.values() if ts[0] or ts[1])

    return ConnectionStatsResponse(
        total=contacts_only + customers_only + linked,
        contacts_only=contacts_only,
        customers_only=customers_only,
        linked=linked,
        by_pipeline_stage=by_pipeline_stage,
        by_customer_status=by_customer_status,
        with_interactions=with_interactions,
    )
