"""Voice A/B Test management API endpoints."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_tenant_context
from app.persistence.database import get_db
from app.persistence.models.voice_ab_test import VoiceABTest, VoiceABTestVariant

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Request/Response Schemas ---

class VariantCreate(BaseModel):
    voice_model: str
    label: str
    is_control: bool = False


class TestCreate(BaseModel):
    name: str
    started_at: str  # ISO datetime
    variants: list[VariantCreate] = []


class TestUpdate(BaseModel):
    name: str | None = None
    status: str | None = None  # active, paused, completed
    ended_at: str | None = None


class VariantResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    voice_model: str
    label: str
    is_control: bool
    created_at: str


class TestResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    status: str
    started_at: str
    ended_at: str | None
    created_at: str
    variants: list[VariantResponse]


# --- Endpoints ---

@router.get("")
async def list_tests(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> list[TestResponse]:
    """List all A/B tests for the current tenant."""
    result = await db.execute(
        select(VoiceABTest)
        .where(VoiceABTest.tenant_id == tenant_id)
        .options(selectinload(VoiceABTest.variants))
        .order_by(VoiceABTest.created_at.desc())
    )
    tests = result.scalars().all()
    return [
        TestResponse(
            id=t.id,
            name=t.name,
            status=t.status,
            started_at=t.started_at.isoformat(),
            ended_at=t.ended_at.isoformat() if t.ended_at else None,
            created_at=t.created_at.isoformat(),
            variants=[
                VariantResponse(
                    id=v.id,
                    voice_model=v.voice_model,
                    label=v.label,
                    is_control=v.is_control,
                    created_at=v.created_at.isoformat(),
                )
                for v in t.variants
            ],
        )
        for t in tests
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_test(
    body: TestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TestResponse:
    """Create a new A/B test with variants."""
    test = VoiceABTest(
        tenant_id=tenant_id,
        name=body.name,
        status="active",
        started_at=datetime.fromisoformat(body.started_at).replace(tzinfo=None),
    )
    db.add(test)
    await db.flush()

    for v in body.variants:
        variant = VoiceABTestVariant(
            test_id=test.id,
            voice_model=v.voice_model,
            label=v.label,
            is_control=v.is_control,
        )
        db.add(variant)

    await db.commit()
    await db.refresh(test, ["variants"])

    return TestResponse(
        id=test.id,
        name=test.name,
        status=test.status,
        started_at=test.started_at.isoformat(),
        ended_at=None,
        created_at=test.created_at.isoformat(),
        variants=[
            VariantResponse(
                id=v.id,
                voice_model=v.voice_model,
                label=v.label,
                is_control=v.is_control,
                created_at=v.created_at.isoformat(),
            )
            for v in test.variants
        ],
    )


@router.get("/{test_id}")
async def get_test(
    test_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TestResponse:
    """Get a single A/B test with variants."""
    result = await db.execute(
        select(VoiceABTest)
        .where(VoiceABTest.id == test_id, VoiceABTest.tenant_id == tenant_id)
        .options(selectinload(VoiceABTest.variants))
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    return TestResponse(
        id=test.id,
        name=test.name,
        status=test.status,
        started_at=test.started_at.isoformat(),
        ended_at=test.ended_at.isoformat() if test.ended_at else None,
        created_at=test.created_at.isoformat(),
        variants=[
            VariantResponse(
                id=v.id,
                voice_model=v.voice_model,
                label=v.label,
                is_control=v.is_control,
                created_at=v.created_at.isoformat(),
            )
            for v in test.variants
        ],
    )


@router.put("/{test_id}")
async def update_test(
    test_id: int,
    body: TestUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> TestResponse:
    """Update an A/B test (name, status, end date)."""
    result = await db.execute(
        select(VoiceABTest)
        .where(VoiceABTest.id == test_id, VoiceABTest.tenant_id == tenant_id)
        .options(selectinload(VoiceABTest.variants))
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    if body.name is not None:
        test.name = body.name
    if body.status is not None:
        if body.status not in ("active", "paused", "completed"):
            raise HTTPException(status_code=400, detail="Invalid status")
        test.status = body.status
    if body.ended_at is not None:
        test.ended_at = datetime.fromisoformat(body.ended_at).replace(tzinfo=None)

    test.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(test, ["variants"])

    return TestResponse(
        id=test.id,
        name=test.name,
        status=test.status,
        started_at=test.started_at.isoformat(),
        ended_at=test.ended_at.isoformat() if test.ended_at else None,
        created_at=test.created_at.isoformat(),
        variants=[
            VariantResponse(
                id=v.id,
                voice_model=v.voice_model,
                label=v.label,
                is_control=v.is_control,
                created_at=v.created_at.isoformat(),
            )
            for v in test.variants
        ],
    )


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    test_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Delete an A/B test and its variants."""
    result = await db.execute(
        select(VoiceABTest).where(VoiceABTest.id == test_id, VoiceABTest.tenant_id == tenant_id)
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    await db.delete(test)
    await db.commit()


@router.post("/{test_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_variant(
    test_id: int,
    body: VariantCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> VariantResponse:
    """Add a variant to an existing test."""
    result = await db.execute(
        select(VoiceABTest).where(VoiceABTest.id == test_id, VoiceABTest.tenant_id == tenant_id)
    )
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    variant = VoiceABTestVariant(
        test_id=test.id,
        voice_model=body.voice_model,
        label=body.label,
        is_control=body.is_control,
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)

    return VariantResponse(
        id=variant.id,
        voice_model=variant.voice_model,
        label=variant.label,
        is_control=variant.is_control,
        created_at=variant.created_at.isoformat(),
    )


@router.delete("/{test_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    test_id: int,
    variant_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int, Depends(require_tenant_context)],
) -> None:
    """Remove a variant from a test."""
    result = await db.execute(
        select(VoiceABTestVariant)
        .join(VoiceABTest)
        .where(
            VoiceABTestVariant.id == variant_id,
            VoiceABTestVariant.test_id == test_id,
            VoiceABTest.tenant_id == tenant_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    await db.delete(variant)
    await db.commit()
