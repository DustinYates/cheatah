"""Do Not Contact (DNC) list management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user
from app.domain.services.dnc_service import DncService
from app.persistence.database import get_db
from app.persistence.models.tenant import User

router = APIRouter()


# Request/Response Models


class DncRecord(BaseModel):
    """DNC record response model."""

    id: int
    phone_number: str | None
    email: str | None
    source_channel: str
    source_message: str | None
    created_at: str
    created_by: int | None

    class Config:
        from_attributes = True


class DncListResponse(BaseModel):
    """Response for DNC list."""

    records: list[DncRecord]
    total: int


class DncCheckResponse(BaseModel):
    """Response for DNC check."""

    is_blocked: bool
    record: DncRecord | None = None


class BlockRequest(BaseModel):
    """Request to block a contact."""

    phone: str | None = None
    email: str | None = None
    reason: str | None = None


class UnblockRequest(BaseModel):
    """Request to unblock a contact."""

    phone: str | None = None
    email: str | None = None
    reason: str | None = None


# Endpoints


@router.get("/list", response_model=DncListResponse)
async def list_dnc(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 100,
) -> DncListResponse:
    """List all blocked contacts for the current tenant.

    Returns paginated list of Do Not Contact records.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    dnc_service = DncService(db)
    records = await dnc_service.list_blocked(tenant_id, skip=skip, limit=limit)
    total = await dnc_service.count_blocked(tenant_id)

    return DncListResponse(
        records=[
            DncRecord(
                id=r.id,
                phone_number=r.phone_number,
                email=r.email,
                source_channel=r.source_channel,
                source_message=r.source_message,
                created_at=r.created_at.isoformat() if r.created_at else "",
                created_by=r.created_by,
            )
            for r in records
        ],
        total=total,
    )


@router.get("/check", response_model=DncCheckResponse)
async def check_dnc(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    phone: str | None = None,
    email: str | None = None,
) -> DncCheckResponse:
    """Check if a phone number or email is on the DNC list.

    At least one of phone or email must be provided.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    if not phone and not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of phone or email must be provided",
        )

    dnc_service = DncService(db)
    record = await dnc_service.get_record(tenant_id, phone=phone, email=email)

    if record:
        return DncCheckResponse(
            is_blocked=True,
            record=DncRecord(
                id=record.id,
                phone_number=record.phone_number,
                email=record.email,
                source_channel=record.source_channel,
                source_message=record.source_message,
                created_at=record.created_at.isoformat() if record.created_at else "",
                created_by=record.created_by,
            ),
        )

    return DncCheckResponse(is_blocked=False, record=None)


@router.post("/block", response_model=DncRecord)
async def block_contact(
    request: BlockRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DncRecord:
    """Manually add a phone number or email to the DNC list.

    At least one of phone or email must be provided.
    Used when a customer verbally requests not to be contacted.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    if not request.phone and not request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of phone or email must be provided",
        )

    dnc_service = DncService(db)
    record = await dnc_service.block(
        tenant_id=tenant_id,
        phone=request.phone,
        email=request.email,
        source_channel="manual",
        source_message=request.reason,
        created_by=current_user.id,
    )

    return DncRecord(
        id=record.id,
        phone_number=record.phone_number,
        email=record.email,
        source_channel=record.source_channel,
        source_message=record.source_message,
        created_at=record.created_at.isoformat() if record.created_at else "",
        created_by=record.created_by,
    )


@router.post("/unblock")
async def unblock_contact(
    request: UnblockRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Remove a phone number or email from the DNC list.

    At least one of phone or email must be provided.
    Requires explicit reason for audit trail.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required",
        )

    if not request.phone and not request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of phone or email must be provided",
        )

    dnc_service = DncService(db)
    success = await dnc_service.unblock(
        tenant_id=tenant_id,
        phone=request.phone,
        email=request.email,
        deactivated_by=current_user.id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active DNC record found for this phone/email",
        )

    return {"success": True, "message": "Contact removed from DNC list"}
