"""Transform raw Jackrabbit customer data into UI-expected account_data format."""

import logging

logger = logging.getLogger(__name__)


def transform_jackrabbit_to_account_data(customer_data: dict | None) -> dict:
    """Transform Jackrabbit customer_data into the account_data schema expected by the UI.

    The UI expects:
    {
        "enrollments": [
            {
                "class_name": "Level 2 - Water Exploration",
                "status": "active",
                "location": "Cypress Spring Pool",
                "schedule": "Mon & Wed 4:30 PM - 5:00 PM",
                "instructor": "Coach Sarah",
                "start_date": "2024-01-15"
            }
        ],
        "balance": 0,
        "member_since": "2024-01-15",
        "enrollment_status": "active"
    }

    Args:
        customer_data: Raw data from Jackrabbit (via Zapier callback).

    Returns:
        Normalized account_data dict for the customers table.
    """
    if not customer_data:
        return {}

    result = {}

    enrollments = _extract_enrollments(customer_data)
    if enrollments:
        result["enrollments"] = enrollments

    balance = _extract_balance(customer_data)
    if balance is not None:
        result["balance"] = balance

    member_since = _extract_member_since(customer_data)
    if member_since:
        result["member_since"] = member_since

    # Derive enrollment_status from enrollments
    if enrollments:
        active_count = sum(1 for e in enrollments if e.get("status") == "active")
        result["enrollment_status"] = "active" if active_count > 0 else "inactive"
    elif "status" in customer_data:
        result["enrollment_status"] = str(customer_data["status"]).lower()

    # Extract address fields
    address = _extract_address(customer_data)
    if address:
        result["address"] = address

    # Extract location code (Jackrabbit "Loc" field)
    location_code = _extract_location_code(customer_data)
    if location_code:
        result["location_code"] = location_code

    # Extract student names
    students = _extract_students(customer_data)
    if students:
        result["students"] = students

    # Pass through extra fields not already handled
    _HANDLED_KEYS = {
        "enrollments", "classes", "enroll", "enrolled_classes",
        "balance", "amount_due", "amount_owed", "account_balance",
        "member_since", "created_date", "start_date", "join_date", "registration_date",
        "status", "name", "email", "phone", "phone_number", "phone1",
        "family_name", "first_name", "last_name",
        "id", "family_id", "fam_id",
        # Address / location / students (handled above)
        "address", "street", "street_address", "mailing_address",
        "city", "state", "zip", "zip_code", "zipcode", "postal_code",
        "loc", "location", "location_code",
        "students", "student_names", "children",
    }
    for key, value in customer_data.items():
        if key.lower() not in _HANDLED_KEYS and value is not None:
            result[key] = value

    return result


def _extract_enrollments(data: dict) -> list[dict]:
    """Extract and normalize enrollment records from Jackrabbit data."""
    raw_enrollments = (
        data.get("enrollments")
        or data.get("classes")
        or data.get("enrolled_classes")
        or data.get("enroll")
        or []
    )

    if not isinstance(raw_enrollments, list):
        if isinstance(raw_enrollments, dict):
            raw_enrollments = [raw_enrollments]
        else:
            return []

    enrollments = []
    for raw in raw_enrollments:
        if not isinstance(raw, dict):
            continue

        enrollment = {
            "class_name": (
                raw.get("class_name")
                or raw.get("className")
                or raw.get("class")
                or raw.get("name")
                or "Unknown Class"
            ),
            "status": _normalize_enrollment_status(
                raw.get("status")
                or raw.get("enrollment_status")
                or raw.get("enrollmentStatus")
                or "active"
            ),
        }

        location = (
            raw.get("location")
            or raw.get("location_name")
            or raw.get("locationName")
            or raw.get("site")
        )
        if location:
            enrollment["location"] = location

        schedule = raw.get("schedule") or raw.get("meeting_schedule")
        if not schedule:
            days = raw.get("days") or raw.get("meeting_days") or raw.get("day")
            start_time = raw.get("start_time") or raw.get("startTime") or raw.get("time")
            end_time = raw.get("end_time") or raw.get("endTime")
            if days and start_time:
                schedule = f"{days} {start_time}"
                if end_time:
                    schedule += f" - {end_time}"
        if schedule:
            enrollment["schedule"] = schedule

        instructor = (
            raw.get("instructor")
            or raw.get("teacher")
            or raw.get("coach")
            or raw.get("instructor_name")
        )
        if instructor:
            enrollment["instructor"] = instructor

        start_date = (
            raw.get("start_date")
            or raw.get("startDate")
            or raw.get("enrollment_date")
            or raw.get("enrollDate")
        )
        if start_date:
            enrollment["start_date"] = str(start_date)

        enrollments.append(enrollment)

    return enrollments


def _normalize_enrollment_status(status: str) -> str:
    """Normalize enrollment status to a standard value."""
    status_lower = str(status).lower().strip()
    status_map = {
        "active": "active",
        "enrolled": "active",
        "current": "active",
        "inactive": "inactive",
        "dropped": "dropped",
        "drop": "dropped",
        "withdrawn": "dropped",
        "completed": "completed",
        "complete": "completed",
        "finished": "completed",
        "waitlist": "waitlist",
        "wait list": "waitlist",
        "waiting": "waitlist",
        "trial": "trial",
    }
    return status_map.get(status_lower, status_lower)


def _extract_balance(data: dict) -> float | None:
    """Extract account balance from Jackrabbit data."""
    for key in ["balance", "amount_due", "amount_owed", "account_balance"]:
        value = data.get(key)
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                continue
    return None


def _extract_member_since(data: dict) -> str | None:
    """Extract member-since date from Jackrabbit data."""
    for key in ["member_since", "created_date", "start_date", "join_date", "registration_date"]:
        value = data.get(key)
        if value:
            return str(value)
    return None


def _extract_address(data: dict) -> dict | None:
    """Extract address fields from Jackrabbit data.

    Returns a dict with street, city, state, zip — or None if nothing found.
    """
    # Try a single combined address field first
    for key in ["address", "street", "street_address", "mailing_address"]:
        val = data.get(key) or data.get(key.title())
        if val:
            break
    else:
        val = None

    city = data.get("city") or data.get("City")
    state = data.get("state") or data.get("State")
    zip_code = data.get("zip") or data.get("Zip") or data.get("zip_code") or data.get("postal_code")

    if not val and not city and not zip_code:
        return None

    result = {}
    if val:
        result["street"] = str(val).strip()
    if city:
        result["city"] = str(city).strip()
    if state:
        result["state"] = str(state).strip()
    if zip_code:
        result["zip"] = str(zip_code).strip()
    return result


def _extract_location_code(data: dict) -> str | None:
    """Extract Jackrabbit location code (Loc field)."""
    for key in ["loc", "Loc", "location_code", "location"]:
        val = data.get(key)
        if val:
            return str(val).strip()
    return None


def _extract_students(data: dict) -> list[str] | None:
    """Extract student names from Jackrabbit data.

    Jackrabbit returns students as a comma-separated string like
    "Sumaiya, Zebadiyah" or as a list.
    """
    for key in ["students", "Students", "student_names", "children"]:
        val = data.get(key)
        if val:
            if isinstance(val, list):
                return [str(s).strip() for s in val if s]
            if isinstance(val, str):
                return [s.strip() for s in val.split(",") if s.strip()]
    return None
