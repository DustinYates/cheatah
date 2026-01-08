"""Data models for scraped business website content."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    """Information about a service or program offered."""

    name: str
    description: str | None = None
    price: str | None = None
    url: str | None = None


class LocationInfo(BaseModel):
    """Information about a business location."""

    name: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    email: str | None = None


class BusinessHours(BaseModel):
    """Business hours for a day or location."""

    day: str | None = None  # e.g., "monday", "tuesday"
    location_name: str | None = None  # If hours vary by location
    open_time: str | None = None  # e.g., "09:00"
    close_time: str | None = None  # e.g., "17:00"
    notes: str | None = None  # e.g., "Lessons only", "Office hours"


class PricingInfo(BaseModel):
    """Pricing information for a service or product."""

    item: str
    price: str | None = None
    frequency: str | None = None  # e.g., "per lesson", "monthly", "per session"
    notes: str | None = None


class FAQPair(BaseModel):
    """A frequently asked question and its answer."""

    question: str
    answer: str


class PolicyInfo(BaseModel):
    """Business policy information."""

    policy_type: str  # e.g., "cancellation", "refund", "makeup", "booking"
    description: str
    details: list[str] | None = None


class ProgramInfo(BaseModel):
    """Information about a class level or program."""

    name: str
    description: str | None = None
    age_range: str | None = None
    skill_level: str | None = None
    prerequisites: str | None = None
    max_class_size: int | None = None
    duration: str | None = None
    registration_url: str | None = None


class ScrapedBusinessData(BaseModel):
    """Complete scraped business data from a website."""

    # Basic info
    business_name: str | None = None
    business_description: str | None = None

    # Contact & locations
    locations: list[LocationInfo] = []

    # Hours
    hours: list[BusinessHours] = []

    # Services & programs
    services: list[ServiceInfo] = []
    programs: list[ProgramInfo] = []

    # Pricing
    pricing: list[PricingInfo] = []

    # FAQs
    faqs: list[FAQPair] = []

    # Policies
    policies: list[PolicyInfo] = []

    # Marketing
    unique_selling_points: list[str] = []
    target_audience: str | None = None

    # Raw content for reference
    raw_content: str | None = None

    # Metadata
    scraped_at: datetime | None = None
    source_url: str | None = None
    pages_scraped: list[str] = []

    def to_db_format(self) -> dict[str, Any]:
        """Convert to format suitable for database storage."""
        return {
            "scraped_services": [s.model_dump() for s in self.services] if self.services else None,
            "scraped_hours": [h.model_dump() for h in self.hours] if self.hours else None,
            "scraped_locations": [loc.model_dump() for loc in self.locations] if self.locations else None,
            "scraped_pricing": [p.model_dump() for p in self.pricing] if self.pricing else None,
            "scraped_faqs": [f.model_dump() for f in self.faqs] if self.faqs else None,
            "scraped_policies": [p.model_dump() for p in self.policies] if self.policies else None,
            "scraped_programs": [p.model_dump() for p in self.programs] if self.programs else None,
            "scraped_unique_selling_points": self.unique_selling_points if self.unique_selling_points else None,
            "scraped_target_audience": self.target_audience,
            "scraped_raw_content": self.raw_content,
            "last_scraped_at": self.scraped_at or datetime.utcnow(),
        }
