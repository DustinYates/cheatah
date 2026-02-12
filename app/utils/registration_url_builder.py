"""Centralized registration URL builder for British Swim School.

This module provides a single source of truth for building registration URLs
with validated location codes and pre-encoded type values.
Supports multiple BSS franchises (Cypress-Spring, Atlanta, etc.).
"""

from typing import Literal

# --- Per-franchise configuration ---
FRANCHISE_CONFIG: dict[str, dict] = {
    "cypress-spring": {
        "base_url": "https://britishswimschool.com/cypress-spring/register/",
        "location_codes": frozenset({"LALANG", "LAFCypress", "24Spring"}),
    },
    "atlanta": {
        "base_url": "https://britishswimschool.com/atlanta/register/",
        "location_codes": frozenset({"LABUCK", "OLDUN", "ROSAAC", "HISDUN"}),
    },
}

# Map tenant_id → franchise slug
# Includes both tenant_number and tenants.id (DB PK) for robustness.
# For tenants 1-3, tenant_number == tenants.id. Tenant 4 has tenants.id=237.
TENANT_TO_FRANCHISE: dict[int, str] = {
    3: "cypress-spring",
    4: "atlanta",       # tenant_number
    237: "atlanta",     # tenants.id (DB PK)
}

# Legacy constants (kept for backward-compat with imports elsewhere)
BASE_REGISTRATION_URL = FRANCHISE_CONFIG["cypress-spring"]["base_url"]

# Union of ALL franchise location codes
ALLOWED_LOCATION_CODES = frozenset().union(
    *(cfg["location_codes"] for cfg in FRANCHISE_CONFIG.values())
)

# Valid type codes - PRE-ENCODED (spaces already as %20)
# These are the FINAL URL tokens - do NOT encode them again
ALLOWED_TYPE_CODES = frozenset({
    # Infant/Toddler levels (no spaces)
    "Tadpole",
    "Swimboree",
    "Seahorse",
    # Child beginner levels (no spaces)
    "Starfish",
    "Minnow",
    # Child intermediate levels (with %20 for spaces)
    "Turtle%201",
    "Turtle%202",
    "Shark%201",
    "Shark%202",
    # Advanced levels (no spaces)
    "Barracuda",
    "Dolphin",
    # Young Adult levels (with %20 for spaces)
    "Young%20Adult%201",
    "Young%20Adult%202",
    "Young%20Adult%203",
    # Adult levels (with %20 for spaces)
    "Adult%20Level%201",
    "Adult%20Level%202",
    "Adult%20Level%203",
})

# Mapping from human-readable names to pre-encoded URL values
LEVEL_NAME_TO_TYPE_CODE = {
    # Direct mappings (no spaces)
    "Tadpole": "Tadpole",
    "Swimboree": "Swimboree",
    "Seahorse": "Seahorse",
    "Starfish": "Starfish",
    "Minnow": "Minnow",
    "Barracuda": "Barracuda",
    "Dolphin": "Dolphin",
    # Mappings with spaces -> pre-encoded
    "Turtle 1": "Turtle%201",
    "Turtle 2": "Turtle%202",
    "Shark 1": "Shark%201",
    "Shark 2": "Shark%202",
    "Young Adult 1": "Young%20Adult%201",
    "Young Adult 2": "Young%20Adult%202",
    "Young Adult 3": "Young%20Adult%203",
    "Adult Level 1": "Adult%20Level%201",
    "Adult Level 2": "Adult%20Level%202",
    "Adult Level 3": "Adult%20Level%203",
    # Also accept the pre-encoded versions directly
    "Turtle%201": "Turtle%201",
    "Turtle%202": "Turtle%202",
    "Shark%201": "Shark%201",
    "Shark%202": "Shark%202",
    "Young%20Adult%201": "Young%20Adult%201",
    "Young%20Adult%202": "Young%20Adult%202",
    "Young%20Adult%203": "Young%20Adult%203",
    "Adult%20Level%201": "Adult%20Level%201",
    "Adult%20Level%202": "Adult%20Level%202",
    "Adult%20Level%203": "Adult%20Level%203",
}


class InvalidLocationCodeError(ValueError):
    """Raised when an invalid location code is provided."""
    pass


class InvalidTypeCodeError(ValueError):
    """Raised when an invalid type code is provided."""
    pass


def _get_franchise_for_location(location_code: str) -> dict | None:
    """Find the franchise config that owns a given location code."""
    for cfg in FRANCHISE_CONFIG.values():
        if location_code in cfg["location_codes"]:
            return cfg
    return None


def build_registration_url(
    location_code: str,
    type_code: str | None = None,
    *,
    tenant_id: int | None = None,
    class_id: str | None = None,
) -> str:
    """Build a valid registration URL with proper encoding.

    This function constructs URLs using pre-encoded type values to avoid
    double-encoding issues. The type codes already contain %20 for spaces.

    Args:
        location_code: A valid location code (e.g. LALANG, LABUCK)
        type_code: Optional swim level type (human-readable or pre-encoded).
        tenant_id: Optional tenant ID to select the correct franchise base URL.
            If None, auto-detects from location_code.
        class_id: Optional Jackrabbit class ID to append to URL.

    Returns:
        A complete, valid registration URL.

    Raises:
        InvalidLocationCodeError: If location_code is not recognized
        InvalidTypeCodeError: If type_code is provided but not recognized
    """
    # Validate location code
    if location_code not in ALLOWED_LOCATION_CODES:
        raise InvalidLocationCodeError(
            f"Invalid location code: '{location_code}'. "
            f"Must be one of: {', '.join(sorted(ALLOWED_LOCATION_CODES))}"
        )

    # Determine base URL from tenant or auto-detect from location code
    base_url = None
    if tenant_id is not None:
        franchise_slug = TENANT_TO_FRANCHISE.get(tenant_id)
        if franchise_slug:
            base_url = FRANCHISE_CONFIG[franchise_slug]["base_url"]

    if base_url is None:
        cfg = _get_franchise_for_location(location_code)
        base_url = cfg["base_url"] if cfg else BASE_REGISTRATION_URL

    # Build URL with location
    url = f"{base_url}?loc={location_code}"

    # Add type if provided
    if type_code is not None:
        # Convert human-readable name to pre-encoded value if needed
        encoded_type = LEVEL_NAME_TO_TYPE_CODE.get(type_code)

        if encoded_type is None:
            # Check if it's already a valid pre-encoded type
            if type_code in ALLOWED_TYPE_CODES:
                encoded_type = type_code
            else:
                raise InvalidTypeCodeError(
                    f"Invalid type code: '{type_code}'. "
                    f"Must be a recognized swim level name."
                )

        # Append type parameter - DO NOT encode again, it's already encoded
        url = f"{url}&type={encoded_type}"

    # Add class_id if provided
    if class_id is not None:
        url = f"{url}&class_id={class_id}"

    return url


def get_type_code_for_level(level_name: str) -> str | None:
    """Get the pre-encoded type code for a human-readable level name.

    Args:
        level_name: Human-readable level name like "Adult Level 3"

    Returns:
        Pre-encoded type code like "Adult%20Level%203", or None if not found
    """
    return LEVEL_NAME_TO_TYPE_CODE.get(level_name)


def is_valid_location_code(location_code: str) -> bool:
    """Check if a location code is valid.

    Args:
        location_code: The location code to validate

    Returns:
        True if valid, False otherwise
    """
    return location_code in ALLOWED_LOCATION_CODES


def is_valid_type_code(type_code: str) -> bool:
    """Check if a type code is valid (either human-readable or pre-encoded).

    Args:
        type_code: The type code to validate

    Returns:
        True if valid, False otherwise
    """
    return type_code in LEVEL_NAME_TO_TYPE_CODE or type_code in ALLOWED_TYPE_CODES
