"""API routes for SMS mass-text templates."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.repositories.sms_template_repository import SmsTemplateRepository

logger = logging.getLogger(__name__)

router = APIRouter()


class SmsTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1)


class SmsTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    body: str | None = Field(None, min_length=1)


class SmsTemplateResponse(BaseModel):
    id: int
    name: str
    body: str
    created_by_user_id: int | None
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, t) -> "SmsTemplateResponse":
        return cls(
            id=t.id,
            name=t.name,
            body=t.body,
            created_by_user_id=t.created_by_user_id,
            created_at=t.created_at.isoformat() if t.created_at else "",
            updated_at=t.updated_at.isoformat() if t.updated_at else "",
        )


class SmsTemplateListResponse(BaseModel):
    templates: list[SmsTemplateResponse]


def _require_tenant(tenant_id: int | None) -> int:
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    return tenant_id


@router.get("", response_model=SmsTemplateListResponse)
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    _user: Annotated[User, Depends(get_current_user)],
) -> SmsTemplateListResponse:
    tid = _require_tenant(tenant_id)
    repo = SmsTemplateRepository(db)
    templates = await repo.list_by_tenant(tid)
    return SmsTemplateListResponse(templates=[SmsTemplateResponse.from_model(t) for t in templates])


@router.post("", response_model=SmsTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: SmsTemplateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    user: Annotated[User, Depends(get_current_user)],
) -> SmsTemplateResponse:
    tid = _require_tenant(tenant_id)
    repo = SmsTemplateRepository(db)
    if await repo.get_by_name(tid, payload.name.strip()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A template with that name already exists")
    try:
        template = await repo.create(
            tenant_id=tid,
            name=payload.name.strip(),
            body=payload.body,
            created_by_user_id=user.id,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A template with that name already exists")
    logger.info(f"Created SMS template id={template.id} tenant={tid}")
    return SmsTemplateResponse.from_model(template)


@router.patch("/{template_id}", response_model=SmsTemplateResponse)
async def update_template(
    template_id: int,
    payload: SmsTemplateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    _user: Annotated[User, Depends(get_current_user)],
) -> SmsTemplateResponse:
    tid = _require_tenant(tenant_id)
    repo = SmsTemplateRepository(db)
    template = await repo.get(tid, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if payload.name and payload.name.strip() != template.name:
        existing = await repo.get_by_name(tid, payload.name.strip())
        if existing and existing.id != template.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A template with that name already exists")
    try:
        template = await repo.update(
            template,
            name=payload.name.strip() if payload.name else None,
            body=payload.body,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A template with that name already exists")
    return SmsTemplateResponse.from_model(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    _user: Annotated[User, Depends(get_current_user)],
) -> None:
    tid = _require_tenant(tenant_id)
    repo = SmsTemplateRepository(db)
    template = await repo.get(tid, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await repo.delete(template)
    await db.commit()
