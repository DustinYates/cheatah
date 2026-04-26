"""Detect registration / booking URLs in arbitrary message text.

The Telnyx AI agent sometimes inlines a registration link into an SMS reply
instead of invoking the dedicated `send_link` / `send_registration_link` tool
endpoint. Tool calls write to `sent_assets`; inline sends do not. This module
gives the message-storage path a way to detect those inline sends so we can
record them in `sent_assets` and keep the conversion dashboard accurate.
"""

from __future__ import annotations

import re

# A registration URL is any HTTP(S) URL whose path/host matches one of the
# franchise registration endpoints we know the agent emits, OR a Jackrabbit
# `/Openings`-style URL. Matched leniently — we only need to recognize the
# URL, not validate it.
_REGISTRATION_URL_HINT = re.compile(
    r"(?:"
    r"britishswimschool\.com/[^/\s]+/register"
    r"|jackrabbitclass\.com/[^\s]*"
    r"|/(?:Openings|openings|regv2)\b"
    r")",
    re.IGNORECASE,
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def find_registration_url(text: str | None) -> str | None:
    """Return the first registration-style URL found in ``text``, else None.

    Trailing punctuation (`.,;:)>]`) is stripped so the result is suitable
    for storage / comparison.
    """
    if not text:
        return None
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:)>]\"'")
        if _REGISTRATION_URL_HINT.search(url):
            return url
    return None


def is_registration_url_message(text: str | None) -> bool:
    """True if ``text`` contains a registration-style URL."""
    return find_registration_url(text) is not None
