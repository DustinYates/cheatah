"""Centralized registration URL builder for British Swim School.

This module provides a single source of truth for building registration URLs
with validated location codes and pre-encoded type values.
"""

from typing import Literal

# Exact base URL - hardcoded, do not modify
BASE_REGISTRATION_URL = "https://britishswimschool.com/cypress-spring/register/"

# Allowed location codes - only these three are valid
ALLOWED_LOCATION_CODES = frozenset({"LALANG", "LAFCypress", "24Spring"})

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


def build_registration_url(
    location_code: str,
    type_code: str | None = None,
) -> str:
    """Build a valid registration URL with proper encoding.

    This function constructs URLs using pre-encoded type values to avoid
    double-encoding issues. The type codes already contain %20 for spaces.

    Args:
        location_code: One of LALANG, LAFCypress, 24Spring
        type_code: Optional swim level type. Can be either:
            - A human-readable name like "Adult Level 3"
            - A pre-encoded value like "Adult%20Level%203"
            If None, only the location parameter is included.

    Returns:
        A complete, valid registration URL like:
        https://britishswimschool.com/cypress-spring/register/?loc=24Spring&type=Adult%20Level%203

    Raises:
        InvalidLocationCodeError: If location_code is not in ALLOWED_LOCATION_CODES
        InvalidTypeCodeError: If type_code is provided but not recognized

    Examples:
        >>> build_registration_url("LAFCypress")
        'https://britishswimschool.com/cypress-spring/register/?loc=LAFCypress'

        >>> build_registration_url("24Spring", "Adult Level 3")
        'https://britishswimschool.com/cypress-spring/register/?loc=24Spring&type=Adult%20Level%203'

        >>> build_registration_url("LALANG", "Tadpole")
        'https://britishswimschool.com/cypress-spring/register/?loc=LALANG&type=Tadpole'
    """
    # Validate location code
    if location_code not in ALLOWED_LOCATION_CODES:
        raise InvalidLocationCodeError(
            f"Invalid location code: '{location_code}'. "
            f"Must be one of: {', '.join(sorted(ALLOWED_LOCATION_CODES))}"
        )

    # Build URL with location
    url = f"{BASE_REGISTRATION_URL}?loc={location_code}"

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
