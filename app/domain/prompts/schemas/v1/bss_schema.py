"""Pydantic schemas for British Swim School tenant configuration."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    """Business contact information."""

    support_phone: str = ""
    support_email: str = ""
    sms_enabled: bool = True
    email_enabled: bool = True


class Location(BaseModel):
    """A business location."""

    code: str = ""
    name: str
    address: str = ""
    is_default: bool = False
    pool_hours: Optional[dict[str, str]] = None  # e.g., {"monday": "3:30 PM - 8:00 PM", "tuesday": "CLOSED"}
    office_hours: Optional[dict[str, str]] = None  # e.g., {"monday_friday": "9:00 AM - 5:00 PM"}


class ProgramBasics(BaseModel):
    """Basic program information."""

    class_duration_minutes: int = 30
    pool_type: str = "indoor"
    pool_temperature_f: list[int] = Field(default_factory=lambda: [84, 86])
    year_round_enrollment: bool = True
    earliest_enrollment_months: int = 3


class Level(BaseModel):
    """A swim level/program."""

    name: str
    description: str = ""
    age_range: Optional[str] = None
    skill_level: Optional[str] = None
    prerequisites: Optional[str] = None


class Levels(BaseModel):
    """Level configuration.

    standard_levels and specialty_programs can be:
    - List of strings: ["Tadpole", "Seahorse", ...]
    - List of Level objects: [{"name": "Tadpole", "description": "..."}, ...]
    """

    standard_levels: list[str | Level] = Field(default_factory=list)
    specialty_programs: list[str | Level] = Field(default_factory=list)
    custom_level_aliases: dict[str, str] = Field(default_factory=dict)

    @property
    def items_count(self) -> int:
        """Return total count of levels."""
        return len(self.standard_levels) + len(self.specialty_programs)


class LevelPlacementRule(BaseModel):
    """Rule for determining appropriate level based on age/experience."""

    condition: str  # e.g., "age 3-4, no experience"
    level: Optional[str] = None  # Alternative field name
    recommended_level: Optional[str] = None  # Original field name
    age_range_months: Optional[list[int]] = None  # e.g., [3, 24] for 3-24 months
    notes: Optional[str] = None

    @property
    def resolved_level(self) -> str:
        """Get the level, supporting both field names."""
        return self.level or self.recommended_level or ""


class LevelPlacementRules(BaseModel):
    """Level placement rules by age group."""

    adult: list[LevelPlacementRule] = Field(default_factory=list)
    teen: list[LevelPlacementRule] = Field(default_factory=list)
    child: list[LevelPlacementRule] = Field(default_factory=list)
    infant: list[LevelPlacementRule] = Field(default_factory=list)


class TuitionItem(BaseModel):
    """Tuition/pricing item."""

    program: str
    price: str
    frequency: str = "monthly"  # "monthly", "per class", "semester"
    notes: Optional[str] = None


class Tuition(BaseModel):
    """Tuition configuration."""

    billing_summary: str = ""
    pricing_rules: list[str] = Field(default_factory=list)
    examples: list[TuitionItem] = Field(default_factory=list)

    @property
    def items_count(self) -> int:
        """Return count of pricing rules and examples."""
        return len(self.pricing_rules) + len(self.examples)


class RegistrationFee(BaseModel):
    """Registration fee structure."""

    single_swimmer: Optional[int] = None
    family_max: Optional[int] = None
    one_time: bool = True
    amount: Optional[str] = None  # Alternative: simple string like "$75"


class Fees(BaseModel):
    """Fee configuration.

    registration_fee can be:
    - A string: "$75 one-time"
    - An object: {"single_swimmer": 60, "family_max": 90, "one_time": true}
    """

    registration_fee: str | RegistrationFee | dict = ""
    other_fees: list[dict] = Field(default_factory=list)


class Discount(BaseModel):
    """Discount/promotion."""

    name: str
    type: str = "other"  # "multi_class", "multi_student", "other"
    description: str = ""
    calculation_notes: Optional[str] = None
    valid_until: Optional[date] = None


class Policy(BaseModel):
    """Business policy."""

    policy_type: str  # "payment", "refunds", "withdrawal_cancellation", etc.
    description: str
    details: list[str] = Field(default_factory=list)


class Policies(BaseModel):
    """Policy configuration."""

    payment: list[str] = Field(default_factory=list)
    refunds: list[str] = Field(default_factory=list)
    withdrawal_cancellation: list[str] = Field(default_factory=list)
    makeup_reschedule: list[str] = Field(default_factory=list)
    trial_classes: list[str] = Field(default_factory=list)
    services_not_offered: list[str] = Field(default_factory=list)

    @property
    def items(self) -> list[str]:
        """Return all policy items flattened."""
        return (
            self.payment
            + self.refunds
            + self.withdrawal_cancellation
            + self.makeup_reschedule
            + self.trial_classes
            + self.services_not_offered
        )


class Registration(BaseModel):
    """Registration configuration."""

    link_policy: str = "do_not_show_unless_requested"
    delivery_methods: list[str] = Field(default_factory=lambda: ["text", "email"])
    registration_link_template: str = ""


class PromptAssembly(BaseModel):
    """Assembly configuration for prompt generation."""

    system_prompt_sections_order: list[str] = Field(
        default_factory=lambda: [
            "role",
            "critical_rules",
            "style",
            "business_info",
            "locations",
            "program_basics",
            "levels",
            "level_placement",
            "level_placement_rules",
            "tuition",
            "fees",
            "discounts",
            "policies",
            "registration",
            "conversation_start",
            "conversation_flow",
            "contact_collection",
            "safety",
        ]
    )
    rendering_rules: dict = Field(
        default_factory=lambda: {
            "omit_empty_fields": True,
            "max_bullets_per_reply_guidance": 8,
        }
    )


class BSSTenantConfig(BaseModel):
    """Complete tenant configuration for British Swim School.

    This schema validates the JSON configuration that admins paste
    for each tenant. It contains all business-specific data.
    """

    schema_version: str = "bss_chatbot_prompt_v1"
    prompt_type: str = "text_chatbot"

    # Tenant identification
    tenant_id: str
    display_name: str

    # Contact information
    contact: ContactInfo = Field(default_factory=ContactInfo)

    # Locations
    locations: list[Location] = Field(default_factory=list)

    # Program information
    program_basics: ProgramBasics = Field(default_factory=ProgramBasics)
    levels: Levels = Field(default_factory=Levels)
    level_placement_rules: LevelPlacementRules = Field(default_factory=LevelPlacementRules)

    # Pricing
    tuition: Tuition = Field(default_factory=Tuition)
    fees: Fees = Field(default_factory=Fees)
    discounts: list[Discount] = Field(default_factory=list)

    # Policies
    policies: Policies = Field(default_factory=Policies)
    registration: Registration = Field(default_factory=Registration)

    # Assembly configuration
    assembly: PromptAssembly = Field(default_factory=PromptAssembly)

    class Config:
        """Pydantic config."""

        extra = "allow"  # Allow extra fields for forward compatibility
