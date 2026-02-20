"""Renderer for converting tenant JSON config to prompt text."""

from typing import Any

from app.domain.prompts.schemas.v1.bss_schema import (
    BSSTenantConfig,
    ContactInfo,
    Discount,
    Fees,
    Level,
    LevelPlacementRule,
    LevelPlacementRules,
    Levels,
    Location,
    Policies,
    ProgramBasics,
    Registration,
    Tuition,
)


def render_business_info(display_name: str, contact: ContactInfo) -> str:
    """Render business info section."""
    lines = [f"## BUSINESS INFORMATION", f"Business Name: {display_name}"]

    if contact.support_phone:
        lines.append(f"Phone: {contact.support_phone}")
    if contact.support_email:
        lines.append(f"Email: {contact.support_email}")

    channels = []
    if contact.sms_enabled:
        channels.append("SMS")
    if contact.email_enabled:
        channels.append("Email")
    if channels:
        lines.append(f"Contact Methods: {', '.join(channels)}")

    return "\n".join(lines)


def render_locations(locations: list[Location]) -> str:
    """Render locations section with hours."""
    if not locations:
        return ""

    lines = ["## LOCATIONS"]
    lines.append("CRITICAL: NEVER make up or guess class times. Only use the pool hours listed below.")
    lines.append("")

    for loc in locations:
        loc_line = f"**{loc.name}**"
        if loc.address:
            loc_line += f" - {loc.address}"
        if loc.is_default:
            loc_line += " (Default)"
        lines.append(loc_line)
        lines.append(f"  Location Code: {loc.code}")

        # Render pool hours if available
        pool_hours = getattr(loc, 'pool_hours', None)
        if pool_hours:
            lines.append("  Pool Hours (Class Time Windows):")
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            for day in days:
                hours = pool_hours.get(day, 'Not specified')
                lines.append(f"    - {day.capitalize()}: {hours}")

        # Render office hours if available
        office_hours = getattr(loc, 'office_hours', None)
        if office_hours:
            lines.append("  Office Hours:")
            if 'monday_friday' in office_hours:
                lines.append(f"    - Monday-Friday: {office_hours['monday_friday']}")
            if 'saturday' in office_hours:
                lines.append(f"    - Saturday: {office_hours['saturday']}")
            if 'sunday' in office_hours:
                lines.append(f"    - Sunday: {office_hours['sunday']}")

        lines.append("")  # Blank line between locations

    lines.append("IMPORTANT: If a customer asks about class times on a day marked CLOSED, inform them that location is not available that day and suggest an alternative location that IS open.")

    return "\n".join(lines)


def render_program_basics(program_basics: ProgramBasics) -> str:
    """Render program basics section."""
    lines = ["## PROGRAM BASICS"]
    lines.append(f"- Class Duration: {program_basics.class_duration_minutes} minutes")
    lines.append(f"- Pool Type: {program_basics.pool_type}")

    if program_basics.pool_temperature_f:
        temp_range = program_basics.pool_temperature_f
        if len(temp_range) == 2:
            lines.append(f"- Pool Temperature: {temp_range[0]}-{temp_range[1]}°F")
        elif len(temp_range) == 1:
            lines.append(f"- Pool Temperature: {temp_range[0]}°F")

    if program_basics.year_round_enrollment:
        lines.append("- Year-Round Enrollment: Yes")
    lines.append(f"- Earliest Enrollment: {program_basics.earliest_enrollment_months} months old")

    return "\n".join(lines)


def _render_level(level: Level | str) -> str:
    """Render a single level (can be string or Level object)."""
    # Handle string levels
    if isinstance(level, str):
        return level

    # Handle Level objects
    parts = [level.name]
    if level.description:
        parts.append(f": {level.description}")
    details = []
    if level.age_range:
        details.append(f"Ages: {level.age_range}")
    if level.skill_level:
        details.append(f"Skill: {level.skill_level}")
    if level.prerequisites:
        details.append(f"Prerequisites: {level.prerequisites}")
    if details:
        parts.append(f" ({', '.join(details)})")
    return "".join(parts)


def render_levels(levels: Levels) -> str:
    """Render levels section."""
    lines = ["## SWIM LEVELS"]

    if levels.standard_levels:
        lines.append("\nStandard Levels:")
        for level in levels.standard_levels:
            lines.append(f"- {_render_level(level)}")

    if levels.specialty_programs:
        lines.append("\nSpecialty Programs:")
        for level in levels.specialty_programs:
            lines.append(f"- {_render_level(level)}")

    if levels.custom_level_aliases:
        lines.append("\nLevel Aliases:")
        for alias, actual in levels.custom_level_aliases.items():
            lines.append(f"- '{alias}' = {actual}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _render_placement_rules(rules: list[LevelPlacementRule], age_group: str) -> list[str]:
    """Render placement rules for an age group."""
    if not rules:
        return []
    lines = [f"\n{age_group}:"]
    for rule in rules:
        # Use resolved_level which handles both 'level' and 'recommended_level' fields
        level = rule.resolved_level
        age_qualifier = ""
        if rule.age_range_months:
            age_qualifier = f" (ages {rule.age_range_months[0]}-{rule.age_range_months[1]} months)"
        line = f"- If {rule.condition}{age_qualifier} → {level}"
        if rule.notes:
            line += f" ({rule.notes})"
        lines.append(line)
    return lines


def render_level_placement_rules(rules: LevelPlacementRules) -> str:
    """Render level placement rules section."""
    lines = ["## LEVEL PLACEMENT RULES"]
    lines.append("Use these rules to recommend the appropriate level:")

    lines.extend(_render_placement_rules(rules.infant, "Infant (under 3)"))
    lines.extend(_render_placement_rules(rules.child, "Child (3-11)"))
    lines.extend(_render_placement_rules(rules.teen, "Teen (12-17)"))
    lines.extend(_render_placement_rules(rules.adult, "Adult (18+)"))

    return "\n".join(lines) if len(lines) > 2 else ""


def render_tuition(tuition: Tuition) -> str:
    """Render tuition section."""
    lines = ["## TUITION & PRICING"]

    if tuition.billing_summary:
        lines.append(tuition.billing_summary)

    if tuition.pricing_rules:
        lines.append("\nPricing Rules:")
        for rule in tuition.pricing_rules:
            lines.append(f"- {rule}")

    if tuition.examples:
        lines.append("\nPricing Examples:")
        for item in tuition.examples:
            line = f"- {item.program}: {item.price}"
            if item.frequency != "monthly":
                line += f" ({item.frequency})"
            if item.notes:
                line += f" - {item.notes}"
            lines.append(line)

    return "\n".join(lines) if len(lines) > 1 else ""


def render_fees(fees: Fees) -> str:
    """Render fees section."""
    lines = ["## FEES"]

    if fees.registration_fee:
        reg_fee = fees.registration_fee
        if isinstance(reg_fee, str):
            lines.append(f"- Registration Fee: {reg_fee}")
        elif isinstance(reg_fee, dict):
            # Handle structured fee object
            single = reg_fee.get("single_swimmer")
            family = reg_fee.get("family_max")
            if single and family:
                lines.append(f"- Registration Fee: ${single} per swimmer, ${family} family max (one-time)")
            elif single:
                lines.append(f"- Registration Fee: ${single} (one-time)")
            elif reg_fee.get("amount"):
                lines.append(f"- Registration Fee: {reg_fee.get('amount')}")
        else:
            # RegistrationFee object
            if hasattr(reg_fee, "single_swimmer") and reg_fee.single_swimmer:
                if reg_fee.family_max:
                    lines.append(f"- Registration Fee: ${reg_fee.single_swimmer} per swimmer, ${reg_fee.family_max} family max (one-time)")
                else:
                    lines.append(f"- Registration Fee: ${reg_fee.single_swimmer} (one-time)")
            elif hasattr(reg_fee, "amount") and reg_fee.amount:
                lines.append(f"- Registration Fee: {reg_fee.amount}")

    if fees.other_fees:
        for fee in fees.other_fees:
            name = fee.get("name", "Fee")
            amount = fee.get("amount", "")
            lines.append(f"- {name}: {amount}")

    return "\n".join(lines) if len(lines) > 1 else ""


def render_discounts(discounts: list[Discount]) -> str:
    """Render discounts section."""
    if not discounts:
        return ""

    lines = ["## DISCOUNTS & PROMOTIONS"]
    for discount in discounts:
        line = f"- {discount.name}: {discount.description}"
        if discount.calculation_notes:
            line += f" ({discount.calculation_notes})"
        lines.append(line)

    return "\n".join(lines)


def render_policies(policies: Policies) -> str:
    """Render policies section."""
    lines = ["## POLICIES"]

    def add_policy_group(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"\n{title}:")
            for item in items:
                lines.append(f"- {item}")

    add_policy_group("Payment Policy", policies.payment)
    add_policy_group("Refund Policy", policies.refunds)
    add_policy_group("Withdrawal/Cancellation", policies.withdrawal_cancellation)
    add_policy_group("Makeup/Reschedule", policies.makeup_reschedule)
    add_policy_group("Trial Classes", policies.trial_classes)
    add_policy_group("Services NOT Offered", policies.services_not_offered)

    return "\n".join(lines) if len(lines) > 1 else ""


def render_registration(registration: Registration) -> str:
    """Render registration section."""
    lines = ["## REGISTRATION"]

    if registration.link_policy == "do_not_show_unless_requested":
        lines.append("Note: Only share registration link when user explicitly asks for it.")
    elif registration.link_policy == "always_show":
        lines.append("Proactively offer registration link after level confirmation.")
    elif registration.link_policy == "send_only_after_level_and_location_confirmed":
        lines.append("IMPORTANT: Only send registration link AFTER confirming both the swimmer's level AND preferred location.")

    if registration.delivery_methods:
        lines.append(f"Link delivery methods: {', '.join(registration.delivery_methods)}")

    if registration.registration_link_template:
        lines.append(f"Registration link template: {registration.registration_link_template}")
        lines.append("Replace {{LOCATION_CODE}} and {{LEVEL_TYPE}} with actual values when sending.")

    return "\n".join(lines) if len(lines) > 1 else ""


def render_section(section_key: str, config: BSSTenantConfig) -> str | None:
    """Render a tenant config section to text.

    Args:
        section_key: The section to render
        config: The tenant configuration

    Returns:
        Rendered text for the section, or None if empty/not applicable
    """
    renderers = {
        "business_info": lambda: render_business_info(config.display_name, config.contact),
        "locations": lambda: render_locations(config.locations),
        "program_basics": lambda: render_program_basics(config.program_basics),
        "levels": lambda: render_levels(config.levels),
        "level_placement_rules": lambda: render_level_placement_rules(config.level_placement_rules),
        "tuition": lambda: render_tuition(config.tuition),
        "fees": lambda: render_fees(config.fees),
        "discounts": lambda: render_discounts(config.discounts),
        "policies": lambda: render_policies(config.policies),
        "registration": lambda: render_registration(config.registration),
    }

    renderer = renderers.get(section_key)
    if renderer:
        result = renderer()
        return result if result else None
    return None
