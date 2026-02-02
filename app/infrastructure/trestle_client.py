"""Trestle IQ reverse phone lookup client.

Used to get accurate caller identity (name, address, email) from phone number
for Jackrabbit registration form pre-fill.

API docs: https://docs.trestleiq.com/api-reference/reverse-phone-api
"""

import logging

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.trestleiq.com/3.2"


async def reverse_phone_lookup(phone: str) -> dict | None:
    """Look up caller identity by phone number via Trestle IQ.

    Args:
        phone: Phone number in E.164 format (e.g. "+12817882316")

    Returns:
        Dict with first_name, last_name, email, address, city, state, zip
        or None if lookup fails or no data found.
    """
    api_key = settings.trestle_api_key
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BASE_URL}/phone",
                params={"phone": phone},
                headers={"x-api-key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract first person from owners array
        owners = data.get("owners") or []
        if not owners:
            logger.info(f"[TRESTLE] No owner data for {phone}")
            return None

        owner = owners[0]
        result: dict[str, str] = {}

        # Name
        if owner.get("firstname"):
            result["first_name"] = owner["firstname"]
        if owner.get("lastname"):
            result["last_name"] = owner["lastname"]

        # Email (first available)
        emails = owner.get("emails") or []
        if emails:
            first_email = emails[0]
            if isinstance(first_email, dict):
                result["email"] = first_email.get("email_address", "")
            elif isinstance(first_email, str):
                result["email"] = first_email

        # Address (first current address)
        addresses = data.get("current_addresses") or owner.get("current_addresses") or []
        if addresses:
            addr = addresses[0]
            street_line = addr.get("street_line_1", "")
            if addr.get("street_line_2"):
                street_line = f"{street_line} {addr['street_line_2']}"
            if street_line:
                result["address"] = street_line
            if addr.get("city"):
                result["city"] = addr["city"]
            if addr.get("state_code"):
                result["state"] = addr["state_code"]
            if addr.get("postal_code"):
                result["zip"] = addr["postal_code"]

        logger.info(
            f"[TRESTLE] Lookup for {phone}: "
            f"name={result.get('first_name', '?')} {result.get('last_name', '?')}, "
            f"email={result.get('email', '?')}, city={result.get('city', '?')}"
        )
        return result if result else None

    except httpx.TimeoutException:
        logger.warning(f"[TRESTLE] Timeout looking up {phone}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"[TRESTLE] HTTP {e.response.status_code} for {phone}")
        return None
    except Exception as e:
        logger.warning(f"[TRESTLE] Unexpected error for {phone}: {e}")
        return None
