"""Build Jackrabbit registration URLs with prefilled customer data.

This module creates registration URLs for Jackrabbit Class that prefill
customer contact information, reducing friction in the enrollment process.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Default Jackrabbit org ID for BSS Cypress-Spring
DEFAULT_ORG_ID = "545911"

# Jackrabbit registration base URL
JACKRABBIT_BASE_URL = "https://app.jackrabbitclass.com/regv2.asp"


@dataclass
class CustomerInfo:
    """Customer information for prefilling registration."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


@dataclass
class StudentInfo:
    """Student information for prefilling registration."""

    first_name: str | None = None
    last_name: str | None = None
    gender: str | None = None  # "M" or "F"
    birth_date: str | None = None  # Format: MM/DD/YYYY
    class_id: str | None = None


def build_jackrabbit_registration_url(
    customer: CustomerInfo | None = None,
    students: list[StudentInfo] | None = None,
    org_id: str = DEFAULT_ORG_ID,
    class_id: str | None = None,
) -> str:
    """Build a Jackrabbit registration URL with prefilled customer data.

    Args:
        customer: Customer contact information to prefill
        students: List of students to prefill (max 5)
        org_id: Jackrabbit organization ID
        class_id: Default class ID for registration

    Returns:
        Complete Jackrabbit registration URL with query parameters

    Example:
        >>> customer = CustomerInfo(first_name="John", last_name="Smith", email="john@email.com")
        >>> build_jackrabbit_registration_url(customer)
        'https://app.jackrabbitclass.com/regv2.asp?id=545911&FamName=Smith&MFName=John&...'
    """
    url_params: dict[str, str] = {"id": org_id}

    if class_id:
        url_params["classid"] = str(class_id)

    # Prefill customer/family contact info
    if customer:
        if customer.last_name:
            url_params["FamName"] = customer.last_name
        if customer.first_name:
            url_params["MFName"] = customer.first_name
        if customer.last_name:
            url_params["MLName"] = customer.last_name
        if customer.email:
            url_params["MEmail"] = customer.email
            url_params["ConfirmMEmail"] = customer.email
        if customer.phone:
            # Format phone for Jackrabbit (digits only or with formatting)
            url_params["MCPhone"] = _format_phone_for_jackrabbit(customer.phone)

        # Address fields
        if customer.address:
            url_params["Addr"] = customer.address
        if customer.city:
            url_params["City"] = customer.city
        if customer.state:
            url_params["State"] = customer.state
        if customer.zip_code:
            url_params["Zip"] = customer.zip_code

    # Always set relationship to "Other" (caller may be any relation)
    url_params["PG1Type"] = "Other"

    # Prefill students (Jackrabbit supports S1-S5, each with classes)
    if students:
        for idx, student in enumerate(students[:5]):  # Max 5 students
            n = idx + 1  # S1, S2, S3...
            if student.first_name:
                url_params[f"S{n}FName"] = student.first_name
            if student.last_name:
                url_params[f"S{n}LName"] = student.last_name
            if student.gender:
                url_params[f"S{n}Gender"] = student.gender
            if student.birth_date:
                url_params[f"S{n}BDate"] = student.birth_date
            if student.class_id:
                url_params[f"S{n}Class"] = str(student.class_id)

    # If no student-level class, use top-level class_id for S1Class
    if "S1Class" not in url_params and class_id:
        url_params["S1Class"] = str(class_id)

    url = f"{JACKRABBIT_BASE_URL}?{urlencode(url_params)}"
    logger.info(f"Built Jackrabbit registration URL with {len(url_params)} params")

    return url


def _format_phone_for_jackrabbit(phone: str) -> str:
    """Format phone number for Jackrabbit.

    Args:
        phone: Phone number in any format

    Returns:
        Formatted phone number
    """
    if not phone:
        return ""

    # Remove common formatting characters but keep the digits
    digits = "".join(c for c in phone if c.isdigit())

    # If it's a US number (10 or 11 digits starting with 1), format nicely
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    # Otherwise return as-is
    return phone


def extract_customer_info_from_lead(lead) -> CustomerInfo:
    """Extract CustomerInfo from a Lead model instance.

    Args:
        lead: Lead model instance with name, email, phone fields

    Returns:
        CustomerInfo dataclass populated from lead data
    """
    first_name = None
    last_name = None

    if lead.name:
        name_parts = lead.name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None

    return CustomerInfo(
        first_name=first_name,
        last_name=last_name,
        email=lead.email,
        phone=lead.phone,
    )
