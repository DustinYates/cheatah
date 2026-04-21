"""Stripe billing service: customers, checkout, portal, subscription sync."""

import logging
import time
from datetime import datetime
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant import Tenant, TenantBusinessProfile
from app.settings import settings

logger = logging.getLogger(__name__)

_PLANS_CACHE: dict[str, Any] = {"plans": None, "expires_at": 0}
_PLANS_CACHE_TTL_SECONDS = 300


def _ensure_stripe_configured() -> None:
    if not settings.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = settings.stripe_secret_key


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        _ensure_stripe_configured()

    async def _get_tenant(self, tenant_id: int) -> Tenant:
        result = await self.session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        return tenant

    async def _get_owner_email(self, tenant_id: int) -> str | None:
        result = await self.session.execute(
            select(TenantBusinessProfile).where(TenantBusinessProfile.tenant_id == tenant_id)
        )
        profile = result.scalar_one_or_none()
        return profile.email if profile else None

    async def get_or_create_customer(self, tenant_id: int) -> str:
        tenant = await self._get_tenant(tenant_id)
        if tenant.stripe_customer_id:
            return tenant.stripe_customer_id

        email = await self._get_owner_email(tenant_id)
        customer = stripe.Customer.create(
            name=tenant.name,
            email=email,
            metadata={"tenant_id": str(tenant_id), "tenant_name": tenant.name},
        )
        tenant.stripe_customer_id = customer.id
        await self.session.commit()
        logger.info(f"Created Stripe customer {customer.id} for tenant {tenant_id}")
        return customer.id

    def list_active_plans(self) -> list[dict[str, Any]]:
        now = time.time()
        if _PLANS_CACHE["plans"] is not None and _PLANS_CACHE["expires_at"] > now:
            return _PLANS_CACHE["plans"]

        prices = stripe.Price.list(active=True, type="recurring", expand=["data.product"], limit=100)
        plans = []
        for price in prices.data:
            product = price.product
            if not getattr(product, "active", True):
                continue
            md = price.metadata.to_dict() if price.metadata else {}
            prod_md = product.metadata.to_dict() if product.metadata else {}
            plans.append({
                "price_id": price.id,
                "product_id": product.id,
                "name": product.name,
                "description": product.description,
                "amount_cents": price.unit_amount,
                "currency": price.currency,
                "interval": price.recurring["interval"] if price.recurring else None,
                "tier": md.get("tier") or prod_md.get("tier"),
                "sms_limit": int(md.get("sms_limit", prod_md.get("sms_limit", 0)) or 0),
                "call_minutes_limit": int(md.get("call_minutes_limit", prod_md.get("call_minutes_limit", 0)) or 0),
                "trial_days": int(md.get("trial_days", 0) or 0),
            })

        tier_order = {"lite": 0, "starter": 1, "essentials": 2, "growth": 3}
        plans.sort(key=lambda p: tier_order.get(p["tier"] or "", 999))

        _PLANS_CACHE["plans"] = plans
        _PLANS_CACHE["expires_at"] = now + _PLANS_CACHE_TTL_SECONDS
        return plans

    async def create_checkout_session(self, tenant_id: int, price_id: str, return_base_url: str) -> str:
        customer_id = await self.get_or_create_customer(tenant_id)

        # Pull trial from price metadata
        price = stripe.Price.retrieve(price_id)
        price_md = price.metadata.to_dict() if price.metadata else {}
        trial_days = int(price_md.get("trial_days", 0) or 0)

        subscription_data: dict[str, Any] = {"metadata": {"tenant_id": str(tenant_id)}}
        if trial_days > 0:
            tenant = await self._get_tenant(tenant_id)
            # Only grant trial if this tenant has never had a subscription before
            if not tenant.stripe_subscription_id:
                subscription_data["trial_period_days"] = trial_days

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            payment_method_types=["card", "us_bank_account"],
            payment_method_collection="always",
            allow_promotion_codes=True,
            subscription_data=subscription_data,
            success_url=f"{return_base_url}?session=success",
            cancel_url=f"{return_base_url}?session=cancel",
            metadata={"tenant_id": str(tenant_id)},
        )
        return session.url

    async def create_portal_session(self, tenant_id: int, return_url: str) -> str:
        customer_id = await self.get_or_create_customer(tenant_id)
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    async def get_subscription_summary(self, tenant_id: int) -> dict[str, Any]:
        tenant = await self._get_tenant(tenant_id)
        summary: dict[str, Any] = {
            "tier": tenant.tier,
            "subscription_status": tenant.subscription_status,
            "current_plan_price_id": tenant.current_plan_price_id,
            "current_period_end": tenant.current_period_end.isoformat() if tenant.current_period_end else None,
            "sms_limit": tenant.sms_limit,
            "call_minutes_limit": tenant.call_minutes_limit,
            "has_payment_method": False,
            "payment_method_brand": None,
            "payment_method_last4": None,
        }

        if not tenant.stripe_subscription_id:
            return summary

        try:
            sub = stripe.Subscription.retrieve(
                tenant.stripe_subscription_id,
                expand=["default_payment_method"],
            )
            pm = sub.default_payment_method
            if pm:
                summary["has_payment_method"] = True
                if pm.type == "card" and pm.card:
                    summary["payment_method_brand"] = pm.card.brand
                    summary["payment_method_last4"] = pm.card.last4
                elif pm.type == "us_bank_account" and pm.us_bank_account:
                    summary["payment_method_brand"] = "ACH"
                    summary["payment_method_last4"] = pm.us_bank_account.last4
        except stripe.error.StripeError as exc:
            logger.warning(f"Failed to retrieve subscription {tenant.stripe_subscription_id}: {exc}")

        return summary

    async def sync_subscription(self, subscription: stripe.Subscription) -> None:
        """Sync a Stripe subscription into the tenant row.

        Reads tier/limits from the price metadata so plans stay configurable in Stripe.
        """
        tenant_id = self._tenant_id_from_subscription(subscription)
        if tenant_id is None:
            logger.warning(f"No tenant_id metadata on subscription {subscription.id}")
            return

        tenant = await self._get_tenant(tenant_id)

        item = subscription["items"]["data"][0] if subscription["items"]["data"] else None
        price = item.price if item else None
        md = price.metadata.to_dict() if (price and price.metadata) else {}

        tenant.stripe_subscription_id = subscription.id
        tenant.subscription_status = subscription.status
        tenant.current_plan_price_id = price.id if price else None
        if subscription.current_period_end:
            tenant.current_period_end = datetime.utcfromtimestamp(subscription.current_period_end)

        if md.get("tier"):
            tenant.tier = md["tier"]
        if md.get("sms_limit"):
            tenant.sms_limit = int(md["sms_limit"])
        if md.get("call_minutes_limit"):
            tenant.call_minutes_limit = int(md["call_minutes_limit"])

        await self.session.commit()
        logger.info(
            f"Synced subscription {subscription.id} for tenant {tenant_id}: "
            f"tier={tenant.tier} status={tenant.subscription_status}"
        )

    async def disable_tenant(self, subscription: stripe.Subscription) -> None:
        """Subscription canceled — downgrade tenant to disabled state."""
        tenant_id = self._tenant_id_from_subscription(subscription)
        if tenant_id is None:
            return

        tenant = await self._get_tenant(tenant_id)
        tenant.subscription_status = "canceled"
        tenant.tier = "disabled"
        tenant.sms_limit = 0
        tenant.call_minutes_limit = 0
        tenant.current_plan_price_id = None
        await self.session.commit()
        logger.info(f"Disabled tenant {tenant_id} after subscription cancellation")

    async def mark_past_due(self, subscription_id: str) -> int | None:
        """Find tenant by subscription_id and mark past_due. Returns tenant_id."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.stripe_subscription_id == subscription_id)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.warning(f"No tenant found for subscription {subscription_id}")
            return None
        tenant.subscription_status = "past_due"
        await self.session.commit()
        return tenant.id

    @staticmethod
    def _tenant_id_from_subscription(subscription: stripe.Subscription) -> int | None:
        md = subscription.metadata.to_dict() if subscription.metadata else {}
        tenant_id_str = md.get("tenant_id")
        if not tenant_id_str:
            return None
        try:
            return int(tenant_id_str)
        except ValueError:
            return None
