"""Derive display tags for a lead from its extra_data.

Tags are computed on the fly (no DB storage) from whatever the email/chat
scraper stored in extra_data. Works retroactively on existing leads.
"""

from __future__ import annotations

import re
from typing import Any

_INFANT_CLASS_TOKENS = {"starfish", "jellyfish", "turtle", "tadpole"}


def derive_tags(
    extra_data: dict[str, Any] | None,
    custom_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build a list of display tags from a lead's extra_data + manual tags.

    Each tag is {"category", "label", "value"} plus optional "editable" flag
    on manual tags so the UI can show a remove button.
    """
    if not isinstance(extra_data, dict):
        extra_data = {}

    tags: list[dict[str, Any]] = []

    audience = _infer_audience(extra_data)
    if audience:
        tags.append({"category": "audience", "label": "Audience", "value": audience})

    zip_code = _extract_zip(extra_data)
    if zip_code:
        tags.append({"category": "zip", "label": "ZIP", "value": zip_code})

    location = _first_nonempty(extra_data, ["location code", "location_code"])
    if location:
        tags.append({"category": "location", "label": "Pool", "value": location})

    class_code = _first_nonempty(extra_data, ["class code", "class_code"])
    if class_code:
        tags.append({"category": "class", "label": "Class", "value": class_code})

    lesson_type = _first_nonempty(extra_data, ["type of lessons", "type_of_lessons"])
    if lesson_type:
        tags.append({"category": "lesson_type", "label": "Lessons", "value": lesson_type})

    heard = _first_nonempty(
        extra_data, ["how did you hear about us?", "how did you hear about us"]
    )
    if heard:
        tags.append({"category": "heard_via", "label": "Heard via", "value": heard})

    source_pill = _build_source_pill(extra_data)
    if source_pill:
        tags.append({"category": "source", "label": "Source", "value": source_pill})

    utm_pill = _build_utm_pill(extra_data)
    if utm_pill:
        tags.append({"category": "utm", "label": "UTM", "value": utm_pill})

    if custom_tags:
        seen: set[str] = set()
        for raw in custom_tags:
            if not isinstance(raw, str):
                continue
            value = raw.strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(
                {
                    "category": "custom",
                    "label": "Tag",
                    "value": value,
                    "editable": True,
                }
            )

    return tags


def _first_nonempty(data: dict[str, Any], keys: list[str]) -> str | None:
    for k in keys:
        v = data.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _infer_audience(data: dict[str, Any]) -> str | None:
    ad_title = (_first_nonempty(data, ["ad title", "ad_title", "ad name", "ad_name"]) or "").lower()
    if "adult" in ad_title:
        return "Adult"
    if ad_title in {"infant", "baby", "toddler"}:
        return "Child (under 3)"
    if ad_title and ad_title not in {"general", "lead"}:
        return "Child"

    lesson_type = (_first_nonempty(data, ["type of lessons", "type_of_lessons"]) or "").lower()
    if "adult" in lesson_type:
        return "Adult"
    if "under 3" in lesson_type or "under3" in lesson_type:
        return "Child (under 3)"
    if "over 3" in lesson_type or "over3" in lesson_type:
        return "Child"

    class_code = (_first_nonempty(data, ["class code", "class_code"]) or "").lower()
    if "adult" in class_code:
        return "Adult"
    if class_code:
        if any(token in class_code for token in _INFANT_CLASS_TOKENS):
            return "Child (under 3)"
        return "Child"

    return None


def _extract_zip(data: dict[str, Any]) -> str | None:
    direct = _first_nonempty(data, ["zipcode", "zip", "zip code", "zip_code", "postal code"])
    if direct:
        match = re.search(r"\b(\d{5})(?:-\d{4})?\b", direct)
        if match:
            return match.group(1)
        return direct

    addr = _first_nonempty(data, ["address"])
    if addr:
        match = re.search(r"\b(\d{5})(?:-\d{4})?\b", addr)
        if match:
            return match.group(1)
    return None


def _build_source_pill(data: dict[str, Any]) -> str | None:
    platform = (_first_nonempty(data, ["platform"]) or "").lower()
    ad_title = _first_nonempty(data, ["ad title", "ad_title", "ad name", "ad_name"])
    if platform:
        channel = {"fb": "Meta FB", "ig": "Meta IG", "facebook": "Meta FB", "instagram": "Meta IG"}.get(
            platform, f"Meta {platform.upper()}"
        )
        return f"{channel} — {ad_title}" if ad_title else channel
    return None


def _build_utm_pill(data: dict[str, Any]) -> str | None:
    parts = [
        _first_nonempty(data, ["utm source", "utm_source"]),
        _first_nonempty(data, ["utm medium", "utm_medium"]),
        _first_nonempty(data, ["utm campaign", "utm_campaign"]),
    ]
    parts = [p for p in parts if p]
    return " / ".join(parts) if parts else None
