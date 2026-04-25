"""Google Ads lead form webhook endpoint.

Accepts a POST from Google Ads' Webhook integration option (Audience Hub →
Lead form extension → Other data integration options) and creates a Lead row
that flows into the same drip + hot-lead notification pipeline as a Zapier
or chat-captured lead.

Authentication is per-tenant: the tenant generates a key (see admin route
`/admin/tenants/{tenant_id}/google-ads/rotate-key`), pastes it into Google
Ads' "Key" field, and Google echoes it back in every payload as `google_key`.
We compare against the value stored on `tenant_business_profiles`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.phone import normalize_phone_e164
from app.domain.services.drip_campaign_service import DripCampaignService
from app.infrastructure.notifications import NotificationService
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import TenantBusinessProfile

logger = logging.getLogger(__name__)

router = APIRouter()


# Map Google Ads `column_id` values to our field names. Google sends these
# as stable identifiers; the matching `column_name` is the human label and
# may be localized.
_KNOWN_COLUMN_IDS = {
    "FULL_NAME", "FIRST_NAME", "LAST_NAME",
    "EMAIL", "PHONE_NUMBER",
    "POSTAL_CODE", "CITY", "REGION", "COUNTRY",
    "JOB_TITLE", "WORK_EMAIL", "WORK_PHONE", "COMPANY_NAME",
}


def _flatten_user_columns(user_column_data: list[dict[str, Any]]) -> dict[str, str]:
    """Turn Google's user_column_data list into a flat dict.

    Each entry has `column_id` (stable, e.g. "EMAIL" or "QUESTION_1"),
    `column_name` (human label, possibly localized), and one of the value
    fields (`string_value`, `int_value`, etc.). We index by both column_id
    and column_name so downstream code can look up either way.
    """
    flat: dict[str, str] = {}
    if not isinstance(user_column_data, list):
        return flat

    for entry in user_column_data:
        if not isinstance(entry, dict):
            continue
        value = (
            entry.get("string_value")
            or entry.get("int_value")
            or entry.get("date_value")
        )
        if value is None or value == "":
            continue
        value_str = str(value).strip()
        if not value_str:
            continue

        col_id = entry.get("column_id")
        col_name = entry.get("column_name")
        if col_id:
            flat[str(col_id)] = value_str
        if col_name and col_name != col_id:
            flat[str(col_name)] = value_str

    return flat


def _resolve_audience_hint(flat: dict[str, str]) -> str | None:
    """Look at qualifying-question answers for an audience hint.

    Google Ads custom questions arrive with `column_id` like "QUESTION_1"
    and the human label in `column_name`. We scan all non-PII columns for
    keywords that match the BSS audience taxonomy.
    """
    text_blobs = []
    for key, value in flat.items():
        if key in _KNOWN_COLUMN_IDS:
            continue
        text_blobs.append(f"{key} {value}".lower())

    blob = " ".join(text_blobs)
    if not blob:
        return None

    if "adult" in blob:
        return "adult"
    if any(token in blob for token in ("under 3", "infant", "baby", "toddler")):
        return "under_3"
    if any(token in blob for token in ("child", "kid", "youth", "minor")):
        return "child"
    return None


def _build_extra_data(
    body: dict[str, Any],
    flat: dict[str, str],
) -> dict[str, Any]:
    """Build the lead's `extra_data` JSON, including audience routing keys."""
    extra: dict[str, Any] = {
        "source": "google_ads",
        "google_lead_id": body.get("lead_id"),
        "form_id": body.get("form_id"),
        "campaign_id": body.get("campaign_id"),
        "adgroup_id": body.get("adgroup_id"),
        "creative_id": body.get("creative_id"),
        "gcl_id": body.get("gcl_id"),
        "api_version": body.get("api_version"),
        "raw_fields": flat,
    }

    # Google sends us the ZIP via POSTAL_CODE — promote it to the key
    # `lead_tagger.infer_audience` / `_extract_zip` looks at.
    if "POSTAL_CODE" in flat:
        extra["zipcode"] = flat["POSTAL_CODE"]

    # Audience routing — `infer_audience` reads `ad title`, `type of lessons`,
    # or `class code`. We don't get those names from Google, so we set
    # `type of lessons` from the qualifying-question answer.
    hint = _resolve_audience_hint(flat)
    if hint == "adult":
        extra["type of lessons"] = "Adult"
    elif hint == "under_3":
        extra["type of lessons"] = "Under 3"
    elif hint == "child":
        extra["type of lessons"] = "Over 3"

    # Drop None values to keep the JSON tidy.
    return {k: v for k, v in extra.items() if v is not None}


async def _find_recent_duplicate(
    session: AsyncSession,
    tenant_id: int,
    phone: str | None,
    email: str | None,
    google_lead_id: str | None,
) -> Lead | None:
    """Find a lead created in the last 24h matching phone/email/google_lead_id."""
    cutoff = datetime.utcnow() - timedelta(hours=24)

    if google_lead_id:
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= cutoff,
        )
        for lead in (await session.execute(stmt)).scalars():
            if (lead.extra_data or {}).get("google_lead_id") == google_lead_id:
                return lead

    if phone:
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.phone == phone,
            Lead.created_at >= cutoff,
        ).order_by(Lead.created_at.desc()).limit(1)
        result = (await session.execute(stmt)).scalar_one_or_none()
        if result:
            return result

    if email:
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.email == email,
            Lead.created_at >= cutoff,
        ).order_by(Lead.created_at.desc()).limit(1)
        result = (await session.execute(stmt)).scalar_one_or_none()
        if result:
            return result

    return None


@router.post("/lead/{tenant_id}")
async def google_ads_lead(
    tenant_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Receive a Google Ads lead form submission.

    URL: `POST /api/v1/google-ads/lead/{tenant_id}`

    The tenant pastes this URL + their generated key into Google Ads UI
    under "Webhook integration". Google validates by sending test data with
    `is_test=true` and the key in `google_key`.
    """
    try:
        body = await request.json()
    except Exception:
        logger.warning(f"google_ads_lead: bad JSON body for tenant {tenant_id}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    # Look up the tenant's stored key.
    profile = (
        await db.execute(
            select(TenantBusinessProfile).where(
                TenantBusinessProfile.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()

    if not profile:
        logger.warning(f"google_ads_lead: tenant {tenant_id} has no business profile")
        raise HTTPException(status_code=404, detail="Tenant not found")

    expected_key = profile.google_ads_webhook_key
    submitted_key = body.get("google_key") or body.get("key")

    if not expected_key:
        logger.warning(
            f"google_ads_lead: tenant {tenant_id} has no webhook key configured"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook key not configured for this tenant",
        )

    if not submitted_key or submitted_key != expected_key:
        logger.warning(
            f"google_ads_lead: invalid key for tenant {tenant_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook key",
        )

    is_test = bool(body.get("is_test"))
    flat = _flatten_user_columns(body.get("user_column_data") or [])

    # Pull the standard contact fields.
    name = flat.get("FULL_NAME")
    if not name:
        first = flat.get("FIRST_NAME")
        last = flat.get("LAST_NAME")
        if first or last:
            name = " ".join(p for p in (first, last) if p)

    email = flat.get("EMAIL") or flat.get("WORK_EMAIL")
    raw_phone = flat.get("PHONE_NUMBER") or flat.get("WORK_PHONE")
    phone = normalize_phone_e164(raw_phone) if raw_phone else None
    google_lead_id = body.get("lead_id")

    extra_data = _build_extra_data(body, flat)
    if is_test:
        extra_data["is_test"] = True

    # For test pings, reuse the most recent test lead from the last hour
    # so repeated "Send test data" clicks don't pile up dozens of rows.
    existing: Lead | None
    if is_test:
        recent_cutoff = datetime.utcnow() - timedelta(hours=1)
        stmt = select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.created_at >= recent_cutoff,
        ).order_by(Lead.created_at.desc())
        existing = None
        for candidate in (await db.execute(stmt)).scalars():
            if (candidate.extra_data or {}).get("is_test"):
                existing = candidate
                break
    else:
        # Dedup real leads against the last 24 hours.
        existing = await _find_recent_duplicate(
            db, tenant_id, phone, email, google_lead_id
        )

    if existing:
        merged = dict(existing.extra_data or {})
        merged.update(extra_data)
        existing.extra_data = merged
        if name and not existing.name:
            existing.name = name
        if phone and not existing.phone:
            existing.phone = phone
        if email and not existing.email:
            existing.email = email
        await db.commit()
        await db.refresh(existing)
        logger.info(
            f"google_ads_lead: merged into existing lead {existing.id} "
            f"for tenant {tenant_id}"
        )
        return JSONResponse(
            content={"status": "merged", "lead_id": existing.id},
            status_code=200,
        )

    custom_tags = ["TEST"] if is_test else []

    lead = Lead(
        tenant_id=tenant_id,
        name=(name or "Google Ads Test") if is_test else name,
        email=email,
        phone=phone,
        status="new",
        pipeline_stage="new_lead",
        extra_data=extra_data,
        custom_tags=custom_tags,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    logger.info(
        f"google_ads_lead: created {'test ' if is_test else ''}lead {lead.id} "
        f"for tenant {tenant_id} (google_lead_id={google_lead_id}, "
        f"phone={phone}, email={email})"
    )

    # Test leads stop here — no drip, no owner SMS. Just return so Ashley
    # sees the row in the dashboard and gets the green check in Google Ads.
    if is_test:
        return JSONResponse(
            content={"status": "test_received", "lead_id": lead.id},
            status_code=200,
        )

    # Drip enrollment — picks the best-matching campaign via audience + tag filters.
    if phone:
        try:
            drip_service = DripCampaignService(db)
            await drip_service.enroll_lead_auto(
                tenant_id=tenant_id,
                lead_id=lead.id,
                context_data={
                    "first_name": name.split()[0] if name else "",
                    "source": "google_ads",
                },
            )
        except Exception as e:
            logger.error(
                f"google_ads_lead: drip enrollment failed for lead {lead.id}: {e}",
                exc_info=True,
            )
            await db.rollback()

    # Owner hot-lead SMS notification.
    try:
        notification_service = NotificationService(db)
        await notification_service.notify_high_intent_lead(
            tenant_id=tenant_id,
            customer_name=name,
            customer_phone=phone,
            customer_email=email,
            channel="google_ads",
            message_preview=(
                f"New Google Ads lead — {name or 'Unknown'} "
                f"({extra_data.get('type of lessons') or 'unspecified audience'})"
            ),
            confidence=1.0,
            keywords=["google_ads_lead"],
            conversation_id=None,
            lead_id=lead.id,
        )
    except Exception as e:
        logger.error(
            f"google_ads_lead: notification failed for lead {lead.id}: {e}",
            exc_info=True,
        )
        await db.rollback()

    return JSONResponse(
        content={"status": "ok", "lead_id": lead.id},
        status_code=200,
    )
