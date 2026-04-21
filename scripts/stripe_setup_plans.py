"""One-time setup: create the 4 ConvoPro Products + Prices in Stripe.

Idempotent — looks up by name, only creates if missing. Safe to re-run.

Usage:
    uv run python scripts/stripe_setup_plans.py
"""

import os
import sys

import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
if not stripe.api_key:
    print("ERROR: STRIPE_SECRET_KEY not set in environment")
    sys.exit(1)


PLANS = [
    {
        "tier": "lite",
        "name": "Lite",
        "description": "Simple, affordable chatbot to get started fast",
        "amount_cents": 3000,
        "trial_days": 30,
        "sms_limit": 0,
        "call_minutes_limit": 0,
    },
    {
        "tier": "starter",
        "name": "Starter",
        "description": "For solopreneurs and small teams getting started",
        "amount_cents": 9900,
        "trial_days": 0,
        "sms_limit": 1000,
        "call_minutes_limit": 0,
    },
    {
        "tier": "essentials",
        "name": "Essentials",
        "description": "For businesses ready to add voice & expand reach",
        "amount_cents": 24900,
        "trial_days": 0,
        "sms_limit": 1500,
        "call_minutes_limit": 200,
    },
    {
        "tier": "growth",
        "name": "Growth",
        "description": "For growing businesses that need every channel covered",
        "amount_cents": 39900,
        "trial_days": 0,
        "sms_limit": 2000,
        "call_minutes_limit": 400,
    },
]


def get_or_create_product(plan: dict) -> stripe.Product:
    existing = stripe.Product.search(query=f"name:'{plan['name']}' AND active:'true'")
    for p in existing.data:
        if p.metadata.get("tier") == plan["tier"]:
            print(f"  product exists: {p.id}")
            return p
    product = stripe.Product.create(
        name=plan["name"],
        description=plan["description"],
        metadata={
            "tier": plan["tier"],
            "sms_limit": str(plan["sms_limit"]),
            "call_minutes_limit": str(plan["call_minutes_limit"]),
        },
    )
    print(f"  product created: {product.id}")
    return product


def get_or_create_price(product: stripe.Product, plan: dict) -> stripe.Price:
    existing = stripe.Price.list(product=product.id, active=True, limit=100)
    for pr in existing.data:
        if (
            pr.unit_amount == plan["amount_cents"]
            and pr.recurring
            and pr.recurring.get("interval") == "month"
        ):
            print(f"  price exists:   {pr.id}")
            return pr
    price = stripe.Price.create(
        product=product.id,
        unit_amount=plan["amount_cents"],
        currency="usd",
        recurring={"interval": "month"},
        metadata={
            "tier": plan["tier"],
            "sms_limit": str(plan["sms_limit"]),
            "call_minutes_limit": str(plan["call_minutes_limit"]),
            "trial_days": str(plan["trial_days"]),
        },
    )
    print(f"  price created:  {price.id}")
    return price


def main() -> None:
    print(f"Stripe mode: {'TEST' if 'test' in stripe.api_key else 'LIVE'}\n")
    results = []
    for plan in PLANS:
        print(f"[{plan['tier']}] {plan['name']} — ${plan['amount_cents'] / 100:.2f}/mo")
        product = get_or_create_product(plan)
        price = get_or_create_price(product, plan)
        results.append({"tier": plan["tier"], "product_id": product.id, "price_id": price.id})
        print()

    print("=" * 60)
    print("PRICE IDS (copy into app/settings.py or env vars)")
    print("=" * 60)
    for r in results:
        print(f"  STRIPE_PRICE_{r['tier'].upper():12} = {r['price_id']}")


if __name__ == "__main__":
    main()
