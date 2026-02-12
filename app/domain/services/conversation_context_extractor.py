"""Extract location and level information from conversation messages for URL building."""

import logging
import re
from dataclasses import dataclass

from app.persistence.models.conversation import Message
from app.utils.registration_url_builder import (
    ALLOWED_LOCATION_CODES,
    LEVEL_NAME_TO_TYPE_CODE,
    build_registration_url,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Extracted context from a conversation."""

    location_code: str | None
    location_name: str | None
    level_name: str | None
    level_type_code: str | None
    registration_url: str | None


# Map location names (as mentioned in conversation) to location codes
LOCATION_NAME_TO_CODE = {
    # --- Cypress-Spring (Tenant 3) ---
    # LA Fitness Langham Creek
    "la fitness langham creek": "LALANG",
    "langham creek": "LALANG",
    "langham": "LALANG",
    "lalang": "LALANG",
    # LA Fitness Cypress
    "la fitness cypress": "LAFCypress",
    "lafcypress": "LAFCypress",
    "cypress": "LAFCypress",
    # 24 Hour Fitness Spring
    "24 hour fitness spring": "24Spring",
    "24 hour fitness in spring": "24Spring",
    "24 hour spring": "24Spring",
    "24spring": "24Spring",
    "spring": "24Spring",
    "24 hr fitness in spring": "24Spring",
    "24 hr spring": "24Spring",
    # --- Atlanta (Tenant 4) ---
    # L.A. Fitness Buckhead
    "la fitness buckhead": "LABUCK",
    "l.a. fitness buckhead": "LABUCK",
    "l. a. fitness buckhead": "LABUCK",
    "buckhead": "LABUCK",
    "labuck": "LABUCK",
    "lenox": "LABUCK",
    # Onelife Fitness Dunwoody / Perimeter
    "onelife fitness dunwoody": "OLDUN",
    "onelife dunwoody": "OLDUN",
    "onelife fitness": "OLDUN",
    "onelife": "OLDUN",
    "perimeter sports club": "OLDUN",
    "perimeter": "OLDUN",
    "dunwoody": "OLDUN",
    "oldun": "OLDUN",
    # Roswell Adult Aquatics Center
    "roswell adult aquatics center": "ROSAAC",
    "roswell aquatics": "ROSAAC",
    "roswell": "ROSAAC",
    "rosaac": "ROSAAC",
    # 4565 Ashford Dunwoody Rd
    "4565 ashford dunwoody": "HISDUN",
    "ashford dunwoody": "HISDUN",
    "ashford": "HISDUN",
    "hisdun": "HISDUN",
}

# Map level names (as mentioned in conversation) to standard level names
LEVEL_NAME_VARIATIONS = {
    # Infant/Toddler
    "tadpole": "Tadpole",
    "swimboree": "Swimboree",
    "seahorse": "Seahorse",
    # Child beginner
    "starfish": "Starfish",
    "minnow": "Minnow",
    # Child intermediate
    "turtle 1": "Turtle 1",
    "turtle 2": "Turtle 2",
    "turtle one": "Turtle 1",
    "turtle two": "Turtle 2",
    # Child advanced
    "shark 1": "Shark 1",
    "shark 2": "Shark 2",
    "shark one": "Shark 1",
    "shark two": "Shark 2",
    # Advanced
    "barracuda": "Barracuda",
    "dolphin": "Dolphin",
    # Young Adult
    "young adult 1": "Young Adult 1",
    "young adult 2": "Young Adult 2",
    "young adult 3": "Young Adult 3",
    "young adult one": "Young Adult 1",
    "young adult two": "Young Adult 2",
    "young adult three": "Young Adult 3",
    "young adult level 1": "Young Adult 1",
    "young adult level 2": "Young Adult 2",
    "young adult level 3": "Young Adult 3",
    # Adult
    "adult level 1": "Adult Level 1",
    "adult level 2": "Adult Level 2",
    "adult level 3": "Adult Level 3",
    "adult 1": "Adult Level 1",
    "adult 2": "Adult Level 2",
    "adult 3": "Adult Level 3",
    "adult one": "Adult Level 1",
    "adult two": "Adult Level 2",
    "adult three": "Adult Level 3",
    "adult level one": "Adult Level 1",
    "adult level two": "Adult Level 2",
    "adult level three": "Adult Level 3",
}


def extract_context_from_messages(messages: list[Message]) -> ConversationContext:
    """Extract location and level information from conversation messages.

    Args:
        messages: List of conversation messages

    Returns:
        ConversationContext with extracted location and level info
    """
    # First, try to find an existing URL in ANY message (search all, most recent first)
    logger.info(f"Searching {len(messages)} messages for registration URL")
    for msg in reversed(messages):
        role = getattr(msg, "role", None) or ""
        content = getattr(msg, "content", None) or str(msg)
        logger.debug(f"Checking message - role={role}, content_length={len(content) if content else 0}")
        if content:
            url = extract_url_from_ai_response(content)
            if url:
                logger.info(f"Found registration URL in conversation: {url}")
                # Extract location and level from the URL itself
                loc_match = re.search(r'loc=([^&]+)', url)
                type_match = re.search(r'type=([^&\s]+)', url)
                return ConversationContext(
                    location_code=loc_match.group(1) if loc_match else None,
                    location_name=None,
                    level_name=type_match.group(1).replace('%20', ' ') if type_match else None,
                    level_type_code=type_match.group(1) if type_match else None,
                    registration_url=url,
                )

    logger.warning("No registration URL found in conversation history")

    # Combine all message content for searching
    all_text = ""
    for msg in messages:
        content = msg.content if hasattr(msg, "content") else str(msg)
        if content:
            all_text += " " + content.lower()

    # Extract location
    location_code = None
    location_name = None
    for name, code in LOCATION_NAME_TO_CODE.items():
        if name in all_text:
            location_code = code
            location_name = name
            logger.debug(f"Found location: {name} -> {code}")
            break

    # Extract level - search for longest matches first to avoid partial matches
    level_name = None
    level_type_code = None
    # Sort by length descending to match "adult level 1" before "adult"
    sorted_levels = sorted(LEVEL_NAME_VARIATIONS.keys(), key=len, reverse=True)
    for variation in sorted_levels:
        if variation in all_text:
            standard_name = LEVEL_NAME_VARIATIONS[variation]
            level_name = standard_name
            level_type_code = LEVEL_NAME_TO_TYPE_CODE.get(standard_name)
            logger.debug(f"Found level: {variation} -> {standard_name} -> {level_type_code}")
            break

    # Build URL if we have at least location
    registration_url = None
    if location_code:
        try:
            registration_url = build_registration_url(location_code, level_name)
            logger.info(f"Built registration URL: {registration_url}")
        except Exception as e:
            logger.warning(f"Failed to build registration URL: {e}")

    return ConversationContext(
        location_code=location_code,
        location_name=location_name,
        level_name=level_name,
        level_type_code=level_type_code,
        registration_url=registration_url,
    )


def extract_url_from_ai_response(ai_response: str) -> str | None:
    """Extract a registration URL directly from an AI response.

    The AI sometimes includes the full URL in its response. This extracts it.

    Args:
        ai_response: The AI's response text

    Returns:
        The extracted URL or None if not found
    """
    # Pattern to match BSS registration URLs (any franchise slug)
    pattern = r'https://britishswimschool\.com/[a-z0-9-]+/register/\?[^\s\)\]\"\'<>]+'
    match = re.search(pattern, ai_response)
    if match:
        url = match.group(0)
        # Clean up any trailing punctuation
        url = url.rstrip('.,;:!?')
        logger.debug(f"Extracted URL from AI response: {url}")
        return url
    return None
