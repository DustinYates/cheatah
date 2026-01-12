"""Update tenant prompt config for tenant 3 (BSS Cypress-Spring)."""

import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROD_DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = PROD_DATABASE_URL

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.persistence.repositories.tenant_prompt_config_repository import TenantPromptConfigRepository
from app.domain.prompts.schemas.v1.bss_schema import BSSTenantConfig
from pydantic import ValidationError

ASYNC_URL = PROD_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(ASYNC_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# User-provided configuration
TENANT_3_CONFIG = {
    "tenant_id": "BSS_CYPRESS_SPRING",
    "display_name": "British Swim School Cypress–Spring",
    "fees": {
        "registration_fee": {
            "one_time": True,
            "family_max": 90,
            "single_swimmer": 60
        },
        "other_fees": []
    },
    "levels": {
        "standard_levels": [
            "Tadpole", "Swimboree", "Seahorse", "Starfish", "Minnow",
            "Turtle 1", "Turtle 2", "Adult Level 1", "Adult Level 2",
            "Adult Level 3", "Young Adult Level 1", "Young Adult Level 2",
            "Young Adult Level 3"
        ],
        "specialty_programs": [
            "Adaptive Aquatics", "Private Lessons", "Barracudas Swim Team"
        ],
        "custom_level_aliases": {}
    },
    "contact": {
        "sms_enabled": True,
        "email_enabled": True,
        "support_email": "",
        "support_phone": ""
    },
    "tuition": {
        "billing_summary": "Tuition is billed monthly and depends on class frequency and number of swimmers.",
        "tuition_details": """Tuition Details
Tuition is billed monthly based on the number of classes per week. It's calculated per lesson, with discounts for multiple classes or siblings. Months with 5 weeks include an extra charge.

IMPORTANT PRICING RULES:
- The sibling discount ONLY applies to the 2nd swimmer and beyond. The first swimmer ALWAYS pays full price.
- When quoting weekly costs, divide monthly total by 4 weeks. Do NOT divide by number of classes.
  Example: 2x/week at $266/month = $66.50 per WEEK (not per class). Per class would be $33.25.

First Swimmer (ALWAYS full price):
1x/week: $35/lesson ($140/month in a 4-week month)
Each additional weekly lesson: $31.50/lesson ($126/month in a 4-week month) – 10% multi-class discount

Each Additional Swimmer (Sibling) - 2nd kid and beyond ONLY:
1x/week: $31.50/lesson ($126/month in a 4-week month) – 10% sibling discount
Each additional weekly lesson: $28.35/lesson ($113.40/month in a 4-week month) – 10% sibling + 10% multi-class discount

Examples (4-week month):

1 swimmer, 1x/week: $140/month ($35/week)
  - One lesson per week: $35 × 4 = $140

1 swimmer, 2x/week: $266/month ($66.50/week, NOT $66.50/class)
  - First lesson: $35 × 4 = $140
  - Second lesson: $31.50 × 4 = $126
  - Total: $266

2 swimmers, 2x/week each: $505.40/month ($126.35/week total, NOT $66.50/class)
  - First swimmer: $266/month = $66.50/week (full price, NO sibling discount)
  - Second swimmer: $239.40/month = $59.85/week (sibling discount applied)
  - Total: $505.40/month = $126.35/week
  - Per class: $505.40 ÷ 16 classes = $31.59/class

3x/week for 1 student: $392/month
3x/week for 2 students: $744.80/month

Billing occurs automatically on the 20th of each month for the next month's lessons, based on exact class count. First month is prorated if starting mid-month. If starting after the 20th, the bill includes prorated current month + full next month.

Registration Fee:
$60 for 1 swimmer or $90 max per family (one-time fee, due at registration)""",
        "pricing_rules": [
            "Billing runs automatically on the twentieth of each month for the following month",
            "First month is prorated if starting mid month",
            "Months with five weeks cost slightly more"
        ],
        "examples": []
    },
    "policies": {
        "payment": ["Active credit card required on file"],
        "refunds": ["No refunds"],
        "trial_classes": [
            "No free trial classes",
            "Families may observe before enrolling"
        ],
        "makeup_reschedule": [
            "Absences must be reported in advance via the app",
            "Makeup lessons are a courtesy and depend on availability",
            "Makeup lessons expire after sixty days",
            "Maximum of three makeup lessons within sixty days"
        ],
        "withdrawal_cancellation": ["Requires thirty days notice"]
    },
    "discounts": [],
    "locations": [
        {
            "code": "LALANG",
            "name": "LA Fitness Langham Creek",
            "address": "17800 FM 529, Houston, TX 77095",
            "is_default": True
        },
        {
            "code": "LAFCYPRESS",
            "name": "LA Fitness Cypress",
            "address": "12304 Barker Cypress Rd., Cypress, TX 77433",
            "is_default": False
        },
        {
            "code": "24SPRING",
            "name": "24 Hour Fitness Spring Energy",
            "address": "1000 Lake Plaza Dr., Spring, TX 77389",
            "is_default": False
        }
    ],
    "registration": {
        "link_policy": "send_only_after_level_and_location_confirmed",
        "delivery_methods": ["text", "email"],
        "registration_link_template": "https://britishswimschool.com/cypress-spring/register/?loc={{LOCATION_CODE}}&type={{LEVEL_TYPE}}"
    },
    "program_basics": {
        "pool_type": "indoor",
        "pool_temperature_f": [84, 86],
        "year_round_enrollment": True,
        "class_duration_minutes": 30,
        "earliest_enrollment_months": 3
    },
    "sendable_assets": {
        "registration_link": {
            "url": "https:www.google.com",
            "enabled": False,
            "sms_template": "Hi {name}! Here's the link you requested: {url}\n"
        }
    },
    "escalation_settings": {
        "enabled": True,
        "custom_keywords": ["speak to a person"],
        "alert_phone_override": None,
        "notification_methods": ["email", "sms"]
    },
    "level_placement_rules": {
        "infant": [
            {
                "level": "Tadpole",
                "condition": "first program or not comfortable",
                "age_range_months": [3, 24]
            },
            {
                "level": "Swimboree",
                "condition": "comfortable and can submerge",
                "age_range_months": [3, 24]
            },
            {
                "level": "Tadpole",
                "condition": "not comfortable or cannot sit independently",
                "age_range_months": [24, 36]
            },
            {
                "level": "Swimboree",
                "condition": "comfortable but cannot float",
                "age_range_months": [24, 36]
            },
            {
                "level": "Seahorse",
                "condition": "can float independently",
                "age_range_months": [24, 36]
            }
        ],
        "child": [
            {
                "level": "Starfish",
                "condition": "first time, cannot submerge, or cannot float"
            },
            {
                "level": "Minnow",
                "condition": "can submerge and float but cannot jump roll float"
            },
            {
                "level": "Turtle 1",
                "condition": "cannot swim freestyle or backstroke"
            },
            {
                "level": "Turtle 2",
                "condition": "can swim freestyle and backstroke"
            }
        ],
        "teen": [
            {
                "level": "Young Adult Level 1",
                "condition": "not comfortable"
            },
            {
                "level": "Young Adult Level 2",
                "condition": "can float but not all strokes"
            },
            {
                "level": "Young Adult Level 3",
                "condition": "knows all four strokes"
            }
        ],
        "adult": [
            {
                "level": "Adult Level 1",
                "condition": "not comfortable or cannot float"
            },
            {
                "level": "Adult Level 2",
                "condition": "can float but not all strokes"
            },
            {
                "level": "Adult Level 3",
                "condition": "knows all four strokes"
            }
        ]
    }
}


async def update_config():
    """Update tenant 3 prompt configuration."""
    print("=" * 70)
    print("UPDATE TENANT 3 PROMPT CONFIGURATION")
    print("=" * 70)
    print()

    # Validate against schema
    try:
        validated_config = BSSTenantConfig.model_validate(TENANT_3_CONFIG)
        print("✅ Configuration validated successfully!")
        print(f"   Display Name: {validated_config.display_name}")
        print(f"   Locations: {len(validated_config.locations or [])}")
        print()
    except ValidationError as e:
        print("❌ Configuration validation failed!")
        print(json.dumps(e.errors(), indent=2))
        return

    async with AsyncSessionLocal() as db:
        repo = TenantPromptConfigRepository(db)

        # Check existing
        existing = await repo.get_by_tenant_id(tenant_id=3)
        if existing:
            print(f"Found existing config (ID: {existing.id})")
            print(f"  Created: {existing.created_at}")
            response = input("Overwrite? (yes/no): ")
            if response.lower() != "yes":
                print("Aborted.")
                return

        # Upsert
        print("Updating configuration...")
        config = await repo.upsert(
            tenant_id=3,
            config_json=TENANT_3_CONFIG,
            schema_version="bss_chatbot_prompt_v1",
            business_type="bss",
        )

        print()
        print("✅ Configuration updated!")
        print(f"   Config ID: {config.id}")
        print(f"   Updated: {config.updated_at}")


if __name__ == "__main__":
    asyncio.run(update_config())
