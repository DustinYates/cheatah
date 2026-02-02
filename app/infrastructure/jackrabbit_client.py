"""Jackrabbit class openings API client with TTL cache."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

JACKRABBIT_OPENINGS_URL = "https://app.jackrabbitclass.com/jr3.0/Openings/OpeningsJson"

_DAY_LABELS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}


def _format_time(t: str | None) -> str:
    """Convert HH:MM 24hr to 12hr like '7:00 PM'."""
    if not t:
        return ""
    try:
        h, m = t.split(":")[:2]
        hour = int(h)
        suffix = "AM" if hour < 12 else "PM"
        if hour == 0:
            hour = 12
        elif hour > 12:
            hour -= 12
        return f"{hour}:{m} {suffix}"
    except (ValueError, IndexError):
        return t


def _format_days(meeting_days) -> str:
    """Convert meeting_days dict to readable string like 'Mon, Wed'."""
    if isinstance(meeting_days, dict):
        return ", ".join(
            label for key, label in _DAY_LABELS.items() if meeting_days.get(key)
        ) or "TBD"
    return str(meeting_days) if meeting_days else "TBD"

# Simple in-memory cache: {org_id: (timestamp, data)}
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def fetch_classes(org_id: str) -> list[dict]:
    """Fetch available classes from Jackrabbit OpeningsJson API.

    Returns a trimmed list of classes with openings > 0.
    Results are cached for 5 minutes to avoid excessive API calls.
    """
    now = time.time()
    cached = _cache.get(org_id)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(JACKRABBIT_OPENINGS_URL, params={"OrgID": org_id})
            resp.raise_for_status()
            raw = resp.json()
            rows = raw.get("rows", []) if isinstance(raw, dict) else raw

        trimmed = []
        for c in rows:
            openings = c.get("openings", {})
            calc = openings.get("calculated_openings", 0)
            if calc <= 0:
                continue
            trimmed.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "location": c.get("location_name"),
                "days": _format_days(c.get("meeting_days")),
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time"),
                "openings": calc,
                "fee": (c.get("tuition") or {}).get("fee"),
            })

        _cache[org_id] = (now, trimmed)
        logger.info(f"Fetched {len(trimmed)} classes with openings from Jackrabbit (org={org_id})")
        return trimmed

    except Exception as e:
        logger.error(f"Failed to fetch Jackrabbit classes (org={org_id}): {e}")
        # Return stale cache if available
        if cached:
            return cached[1]
        return []


def format_classes_for_prompt(classes: list[dict]) -> str:
    """Format class data into a concise string for LLM prompt injection."""
    if not classes:
        return ""

    # Group by location
    by_location: dict[str, list[dict]] = {}
    for c in classes:
        loc = c.get("location") or "Unknown"
        by_location.setdefault(loc, []).append(c)

    lines = ["CURRENT CLASS SCHEDULE (real-time availability from Jackrabbit):"]
    for location, loc_classes in sorted(by_location.items()):
        lines.append(f"\n{location}:")
        for c in sorted(loc_classes, key=lambda x: (x.get("name", ""), x.get("days", ""))):
            fee_str = f", ${c['fee']}/mo" if c.get("fee") else ""
            start = _format_time(c.get("start_time"))
            end = _format_time(c.get("end_time"))
            lines.append(
                f"  - {c['name']} | {c['days']} {start}-{end} "
                f"| {c['openings']} spot(s){fee_str} | class_id={c['id']}"
            )

    lines.append(
        "\nIMPORTANT: Use this schedule data to answer questions about class times, "
        "availability, and days. When a customer asks about schedule or timings, "
        "share the specific days and times from this data. "
        "Do NOT deflect schedule questions to a registration link."
    )
    return "\n".join(lines)
