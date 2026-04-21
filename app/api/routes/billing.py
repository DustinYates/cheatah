"""Stripe billing routes: plans, subscription, checkout, portal, webhook."""

import logging
from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_admin, require_tenant_context
from app.domain.services.billing_service import BillingService
from app.persistence.database import get_db, get_db_no_rls
from app.persistence.models.tenant import User
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class PlanResponse(BaseModel):
    price_id: str
    product_id: str
    name: str
    description: str | None
    amount_cents: int | None
    currency: str
    interval: str | None
    tier: str | None
    sms_limit: int
    call_minutes_limit: int
    trial_days: int


class SubscriptionResponse(BaseModel):
    tier: str | None
    subscription_status: str | None
    current_plan_price_id: str | None
    current_period_end: str | None
    sms_limit: int | None
    call_minutes_limit: int | None
    has_payment_method: bool
    payment_method_brand: str | None
    payment_method_last4: str | None


class CheckoutRequest(BaseModel):
    price_id: str


class RedirectResponse(BaseModel):
    url: str


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlanResponse]:
    """List active subscription plans available for purchase."""
    service = BillingService(db)
    return [PlanResponse(**p) for p in service.list_active_plans()]


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    tenant_id: Annotated[int, Depends(require_tenant_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionResponse:
    """Get current tenant's subscription state and payment method summary."""
    service = BillingService(db)
    summary = await service.get_subscription_summary(tenant_id)
    return SubscriptionResponse(**summary)


@router.post("/checkout-session", response_model=RedirectResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    """Create a Stripe Checkout session for the selected plan. Tenant admin only."""
    _user, tenant_id = auth
    service = BillingService(db)
    try:
        url = await service.create_checkout_session(
            tenant_id=tenant_id,
            price_id=body.price_id,
            return_base_url=settings.stripe_portal_return_url,
        )
    except stripe.error.StripeError as exc:
        logger.error(f"Stripe checkout session create failed: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.user_message or exc))
    return RedirectResponse(url=url)


@router.post("/portal-session", response_model=RedirectResponse)
async def create_portal_session(
    auth: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    """Create a Stripe Customer Portal session for managing payment methods + subscription."""
    _user, tenant_id = auth
    service = BillingService(db)
    try:
        url = await service.create_portal_session(
            tenant_id=tenant_id,
            return_url=settings.stripe_portal_return_url,
        )
    except stripe.error.StripeError as exc:
        logger.error(f"Stripe portal session create failed: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.user_message or exc))
    return RedirectResponse(url=url)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="stripe-signature")] = None,
) -> dict[str, Any]:
    """Stripe webhook handler. Verifies signature, syncs subscription state.

    Public endpoint — uses no-RLS DB session to update any tenant.
    """
    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured — refusing webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature or "",
            secret=settings.stripe_webhook_secret,
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning(f"Invalid Stripe webhook signature: {exc}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    obj = event["data"]["object"]
    logger.info(f"Stripe webhook: {event_type} (id={event['id']})")

    async for db in get_db_no_rls():
        service = BillingService(db)
        try:
            if event_type in ("customer.subscription.created", "customer.subscription.updated"):
                await service.sync_subscription(obj)
            elif event_type == "customer.subscription.deleted":
                await service.disable_tenant(obj)
            elif event_type == "invoice.payment_failed":
                sub_id = obj["subscription"] if "subscription" in obj else None
                if sub_id:
                    tenant_id = await service.mark_past_due(sub_id)
                    if tenant_id:
                        await _send_payment_failed_alert(db, tenant_id)
            elif event_type == "invoice.payment_succeeded":
                # subscription.updated handles state — nothing to do here
                pass
            else:
                logger.debug(f"Ignoring Stripe event: {event_type}")
        except Exception as exc:
            logger.error(f"Error handling Stripe webhook {event_type}: {exc}", exc_info=True)
            # Return 500 so Stripe retries
            raise HTTPException(status_code=500, detail="Webhook handler error")
        break

    return {"received": True}


async def _send_payment_failed_alert(db: AsyncSession, tenant_id: int) -> None:
    """Notify tenant owner via SMS that their payment failed."""
    from app.infrastructure.notifications import NotificationService
    from app.persistence.models.notification import NotificationPriority, NotificationType
    from app.persistence.models.notification import Notification
    from app.persistence.models.tenant import TenantBusinessProfile
    from sqlalchemy import select

    # Get owner phone
    result = await db.execute(
        select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()
    owner_phone = profile.owner_phone if profile else None

    message = (
        "ConvoPro: Your last payment failed. "
        "Please update your payment method in Settings → Billing to avoid service interruption."
    )

    # In-app notification
    notif = Notification(
        tenant_id=tenant_id,
        user_id=None,
        notification_type=NotificationType.SYSTEM,
        title="Payment failed",
        message=message,
        extra_data={"reason": "stripe_payment_failed"},
        priority=NotificationPriority.HIGH,
        is_read=False,
    )
    db.add(notif)
    await db.commit()

    # SMS via existing helper
    if owner_phone:
        try:
            svc = NotificationService(db)
            await svc._send_lead_notification_sms(  # noqa: SLF001 — reusing existing helper
                tenant_id=tenant_id,
                message=message,
                lead_notification_settings={"phone": owner_phone},
            )
        except Exception as exc:
            logger.error(f"Failed to send payment_failed SMS to tenant {tenant_id}: {exc}")
