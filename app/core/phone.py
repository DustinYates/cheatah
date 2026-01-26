"""Phone number utilities for consistent handling across the application."""


def normalize_phone_for_dedup(phone: str) -> str:
    """Normalize phone to last 10 digits for deduplication.

    This ensures consistent dedup keys across all services.
    The last 10 digits are used because:
    - US phone numbers are 10 digits (area code + 7 digits)
    - This strips country code (+1) and any formatting
    - Ensures consistent matching regardless of input format

    Examples:
        +12817882316 → 2817882316
        12817882316 → 2817882316
        (281) 788-2316 → 2817882316
        281-788-2316 → 2817882316

    Args:
        phone: Phone number in any format

    Returns:
        Last 10 digits of the phone number
    """
    return "".join(c for c in phone if c.isdigit())[-10:]
