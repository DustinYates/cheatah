"""Phone number utilities for consistent handling across the application."""

import logging
import re

logger = logging.getLogger(__name__)


def normalize_phone_e164(phone: str | None) -> str | None:
    """Normalize phone number to E.164 format (+1XXXXXXXXXX for US numbers).

    Handles various input formats:
        (281)788-2316 → +12817882316
        281-788-2316  → +12817882316
        +1 281 788 2316 → +12817882316
        1-281-788-2316 → +12817882316

    Returns:
        Phone in E.164 format (+1XXXXXXXXXX) or None if invalid
    """
    if not phone:
        return None

    digits = re.sub(r'\D', '', phone)

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif len(digits) > 10 and phone.strip().startswith('+'):
        return f"+{digits}"

    if phone.startswith('+') and len(digits) >= 10:
        return f"+{digits}"

    logger.warning(f"Could not normalize phone number: {phone}")
    return phone


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
