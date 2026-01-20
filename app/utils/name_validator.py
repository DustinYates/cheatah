"""Strict name validation utility for lead capture."""

import re
import logging

logger = logging.getLogger(__name__)

# Common short acknowledgements that should NOT be accepted as names
ACKNOWLEDGEMENT_WORDS = {
    # Affirmatives
    "yes", "yep", "yeah", "yea", "yup", "ya", "aye",
    "ok", "okay", "k", "kk", "okey",
    "sure", "alright", "aight",
    "good", "great", "nice", "cool", "fine", "perfect", "awesome", "excellent",
    "thanks", "thank", "thx", "ty", "thank you", "thankyou",
    "please", "pls", "plz",
    # Negatives
    "no", "nope", "nah", "na", "nay",
    # Common short responses
    "can", "will", "would", "could", "should", "may", "might",
    "maybe", "perhaps", "possibly",
    # Greetings
    "hello", "hi", "hey", "hiya", "howdy", "yo",
    "bye", "goodbye", "cya", "later",
    # Common filler words
    "um", "uh", "hmm", "hm", "ah", "oh", "eh",
    "well", "so", "like", "just",
    # Question words (shouldn't be names alone)
    "what", "when", "where", "who", "why", "how",
    # Generic terms
    "name", "email", "phone", "address", "contact",
    "test", "testing", "demo",
    "unknown", "anonymous", "none", "null", "n/a", "na", "nil",
    # Single letters/very short
    "a", "b", "c", "i", "u", "r", "y", "n",
}

# Common pronouns that should NOT appear as last name components
# These often get incorrectly captured when users say things like:
# "Ashley" followed by "He loves to swim" -> incorrectly extracted as "Ashley He"
PRONOUN_SUFFIXES = {
    "he", "she", "they", "him", "her", "them",
    "his", "hers", "their", "theirs",
    "it", "its",
}

# Words that are clearly NOT surnames and should be stripped when appearing
# as the last word of a multi-word name. This catches cases like:
# "Ashley No" (from "No prior experience") or "John Yes" (from "Yes, I'm interested")
# Note: We exclude words like "will" that could be legitimate surnames (Will Smith)
NON_SURNAME_SUFFIXES = {
    # Negatives - clearly not surnames
    "no", "nope", "nah", "na", "nay", "not",
    # Affirmatives - clearly not surnames
    "yes", "yep", "yeah", "yea", "yup", "ya", "aye",
    # Acknowledgements - clearly not surnames
    "ok", "okay", "k", "kk", "okey",
    "sure", "alright", "aight",
    # Common conversation words that get concatenated
    "thanks", "thank", "thx", "please", "pls",
    "hello", "hi", "hey", "bye",
    # Question/response starters
    "what", "when", "where", "who", "why", "how",
    "well", "so", "just", "like",
    # Short words that are never surnames
    "um", "uh", "hmm", "ah", "oh", "eh",
    "i", "we", "my", "me",
    # Topic/business words that get incorrectly concatenated with names
    # e.g., "Tarnisha Pricing" from separate messages about pricing
    "pricing", "prices", "price", "cost", "costs", "rate", "rates", "fee", "fees",
    "schedule", "schedules", "scheduling", "availability", "hours", "times",
    "registration", "registrations", "enrollment", "enroll",
    "information", "info", "details",
    "class", "classes", "lesson", "lessons", "session", "sessions",
    "program", "programs", "level", "levels",
    "swimming", "swim", "location", "locations",
    "payment", "payments", "question", "questions",
    # Common adjectives/state descriptors that get incorrectly captured as surnames
    # e.g., "Jamiyah Comfortable" from "I'm comfortable floating"
    "comfortable", "interested", "able", "available", "ready", "happy", "excited",
    "nervous", "afraid", "good", "great", "fine", "doing", "feeling", "trying",
    "learning", "starting", "new", "beginner", "intermediate", "advanced", "experienced",
}

# Patterns that indicate non-name content
URL_PATTERN = re.compile(r'https?://|www\.|\.com|\.org|\.net|\.io', re.IGNORECASE)
EMAIL_PATTERN = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}')
PHONE_PATTERN = re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE
)


def validate_name(name: str | None, require_explicit: bool = False) -> str | None:
    """Validate and clean a name string with strict rules.

    Args:
        name: The name string to validate
        require_explicit: If True, requires the name to have been explicitly
                         provided (e.g., from a form field or "my name is X")

    Returns:
        Cleaned name if valid, None if invalid
    """
    if not name:
        return None

    # Basic cleanup
    name = name.strip()
    name = ' '.join(name.split())  # Normalize whitespace

    # Remove angle brackets
    name = re.sub(r'[<>]', '', name).strip()

    # Length checks
    if len(name) < 2:
        logger.debug(f"Name rejected (too short): '{name}'")
        return None

    if len(name) > 60:
        logger.debug(f"Name rejected (too long): '{name}'")
        return None

    # Check for URLs
    if URL_PATTERN.search(name):
        logger.debug(f"Name rejected (contains URL): '{name}'")
        return None

    # Check for email patterns
    if EMAIL_PATTERN.search(name):
        logger.debug(f"Name rejected (contains email): '{name}'")
        return None

    # Check for phone patterns
    if PHONE_PATTERN.search(name):
        logger.debug(f"Name rejected (contains phone): '{name}'")
        return None

    # Check for emojis
    if EMOJI_PATTERN.search(name):
        logger.debug(f"Name rejected (contains emoji): '{name}'")
        return None

    # Check against acknowledgement words (case-insensitive)
    name_lower = name.lower().strip()
    if name_lower in ACKNOWLEDGEMENT_WORDS:
        logger.debug(f"Name rejected (common acknowledgement): '{name}'")
        return None

    # Check if name starts with an acknowledgment/filler word (common extraction error)
    # e.g., "Fine Emilio" where "Fine" came from "Fine, my name is Emilio"
    # e.g., "Good Sarah" where "Good" came from "Good morning, I'm Sarah"
    name_parts = name_lower.split()
    if len(name_parts) > 1 and name_parts[0] in ACKNOWLEDGEMENT_WORDS:
        # Strip the invalid prefix and keep the rest
        cleaned_parts = name_parts[1:]
        cleaned_name = ' '.join(cleaned_parts)
        logger.info(f"Name cleaned (invalid prefix removed): '{name}' -> '{cleaned_name}'")
        # Re-validate the cleaned name
        return validate_name(cleaned_name, require_explicit=require_explicit)

    # Check if name ends with a pronoun or non-surname word (common extraction error)
    # e.g., "Ashley He" where "He" came from "He loves to swim..."
    # e.g., "Ashley No" where "No" came from "No prior experience"
    invalid_suffixes = PRONOUN_SUFFIXES | NON_SURNAME_SUFFIXES
    if len(name_parts) > 1 and name_parts[-1] in invalid_suffixes:
        # Strip the invalid suffix and keep just the first part(s)
        cleaned_parts = name_parts[:-1]
        cleaned_name = ' '.join(cleaned_parts)
        logger.info(f"Name cleaned (invalid suffix removed): '{name}' -> '{cleaned_name}'")
        # Re-validate the cleaned name
        return validate_name(cleaned_name, require_explicit=require_explicit)

    # Check if mostly non-letters (allow spaces, hyphens, apostrophes, periods)
    # Names should be predominantly letters
    letters_only = re.sub(r"[^a-zA-Z]", "", name)
    if len(letters_only) == 0:
        logger.debug(f"Name rejected (no letters): '{name}'")
        return None

    # Allow reasonable ratio of letters to total chars
    # (spaces, hyphens, apostrophes are allowed)
    allowed_chars = re.sub(r"[^a-zA-Z\s\-'.]", "", name)
    if len(allowed_chars) < len(name) * 0.8:
        logger.debug(f"Name rejected (too many special chars): '{name}'")
        return None

    # Single short token check
    # Reject single tokens of 3 chars or less unless explicitly provided
    tokens = name.split()
    if len(tokens) == 1 and len(name) <= 3 and not require_explicit:
        logger.debug(f"Name rejected (single short token without explicit context): '{name}'")
        return None

    # Check for all-digit content
    if name.replace(' ', '').replace('-', '').isdigit():
        logger.debug(f"Name rejected (all digits): '{name}'")
        return None

    # Title case the name for consistency
    # Handle names with apostrophes and hyphens properly
    def title_case_name(n: str) -> str:
        parts = []
        for part in n.split():
            if '-' in part:
                # Handle hyphenated names like "Smith-Jones"
                parts.append('-'.join(p.capitalize() for p in part.split('-')))
            elif "'" in part:
                # Handle names like "O'Brien" or "D'Angelo"
                idx = part.index("'")
                if idx == 1:
                    # O'Brien -> O'Brien
                    parts.append(part[0].upper() + "'" + part[idx+1:].capitalize())
                else:
                    parts.append(part.capitalize())
            else:
                parts.append(part.capitalize())
        return ' '.join(parts)

    cleaned_name = title_case_name(name)
    logger.debug(f"Name accepted: '{cleaned_name}'")
    return cleaned_name


def extract_name_from_explicit_statement(text: str) -> str | None:
    """Extract a name from explicit statements like "My name is X".

    Args:
        text: The text to search for explicit name statements

    Returns:
        Extracted name if found and valid, None otherwise
    """
    if not text:
        return None

    # Patterns for explicit name statements
    patterns = [
        r"(?:my|the)\s+name\s+is\s+([A-Za-z][A-Za-z\s\-'\.]+)",
        r"(?:i'm|i am|im)\s+([A-Za-z][A-Za-z\s\-'\.]+?)(?:\s*[,.]|\s+and\s|\s+from\s|$)",
        r"this\s+is\s+([A-Za-z][A-Za-z\s\-'\.]+?)(?:\s*[,.]|\s+calling|\s+from\s|$)",
        r"(?:call\s+me|you\s+can\s+call\s+me)\s+([A-Za-z][A-Za-z\s\-'\.]+)",
        r"(?:actually\s+)?(?:my\s+name\s*(?:is|'s)?|i'm)\s+([A-Za-z][A-Za-z\s\-'\.]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            potential_name = match.group(1).strip()
            # Validate with explicit flag
            validated = validate_name(potential_name, require_explicit=True)
            if validated:
                logger.debug(f"Extracted explicit name: '{validated}' from statement")
                return validated

    return None


def is_valid_name_for_display(name: str | None) -> bool:
    """Check if a name is valid for display purposes.

    Args:
        name: The name to check

    Returns:
        True if the name is valid for display, False otherwise
    """
    if not name:
        return False

    # Use the same validation as validate_name but return boolean
    return validate_name(name) is not None
