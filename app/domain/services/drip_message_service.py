"""Service for drip campaign message rendering and response classification."""

import logging
import re

from app.llm.orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

# Template variable patterns: {{Variable Name}}
_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{([^}]+)\}\}")

# Map template variable names to context_data keys
_VARIABLE_MAP = {
    "first name": "first_name",
    "parent first name": "first_name",
    "child name": "child_name",
    "class time": "class_time",
    "location": "location",
    "price": "price",
    "registration url": "registration_url",
    "availability": "availability",
}

# Fallback values when context data is missing
_FALLBACK_VALUES = {
    "first_name": "there",
    "child_name": "your child",
    "location": "our facility",
    "class_time": "",
    "price": "",
    "registration_url": "",
    "availability": "",
}


class DripMessageService:
    """Handles template rendering, availability checks, and response classification."""

    def __init__(self) -> None:
        self.llm_orchestrator = LLMOrchestrator()

    def render_template(self, template: str, context_data: dict | None) -> str:
        """Replace {{Variable Name}} placeholders with values from context_data.

        Missing variables use fallback values. If the fallback is empty string,
        the placeholder and any surrounding whitespace is cleaned up.
        """
        context = context_data or {}

        def replace_var(match: re.Match) -> str:
            var_name = match.group(1).strip().lower()
            context_key = _VARIABLE_MAP.get(var_name, var_name.replace(" ", "_"))
            value = context.get(context_key) or _FALLBACK_VALUES.get(context_key, "")
            return value

        rendered = _TEMPLATE_VAR_PATTERN.sub(replace_var, template)
        # Clean up double spaces from removed variables
        rendered = re.sub(r"  +", " ", rendered)
        # Clean up trailing spaces before punctuation
        rendered = re.sub(r" +([.!?])", r"\1", rendered)
        return rendered.strip()

    async def render_with_availability(
        self,
        template: str,
        context_data: dict | None,
        tenant_id: int,
        fallback_template: str | None,
    ) -> str:
        """Render a template with live Jackrabbit class availability data.

        If availability data can be fetched, injects it into the template.
        Falls back to fallback_template if the check fails.
        """
        context = dict(context_data) if context_data else {}

        try:
            from app.infrastructure.jackrabbit_client import fetch_classes

            # Get org_id from tenant config
            org_id = await self._get_org_id(tenant_id)
            if not org_id:
                logger.warning(f"No org_id found for tenant {tenant_id}, using fallback")
                if fallback_template:
                    return self.render_template(fallback_template, context)
                return self.render_template(template, context)

            classes = await fetch_classes(org_id)

            if classes:
                # Try to find a matching class from context
                target_location = context.get("location", "").lower()
                relevant = [
                    c for c in classes
                    if (not target_location or target_location in c.get("location", "").lower())
                    and c.get("openings", 0) > 0
                ]

                if relevant:
                    cls = relevant[0]
                    avail_text = (
                        f"{cls['name']} on {cls['days']} at {cls.get('start_time', '')} "
                        f"has {cls['openings']} spot(s) available"
                    )
                    context["availability"] = avail_text
                    return self.render_template(template, context)

            # No matching availability — use fallback
            if fallback_template:
                return self.render_template(fallback_template, context)
            return self.render_template(template, context)

        except Exception as e:
            logger.error(f"Availability check failed for tenant {tenant_id}: {e}")
            if fallback_template:
                return self.render_template(fallback_template, context)
            return self.render_template(template, context)

    def classify_response(self, message_text: str, response_templates: dict) -> str:
        """Classify a lead's response into a category using keyword matching.

        Args:
            message_text: The inbound SMS text from the lead.
            response_templates: Dict of category → {keywords, reply/action}.

        Returns:
            Category name: "price", "spouse", "schedule", "sibling",
            "yes_link", "not_interested", or "other".
        """
        text_lower = message_text.lower().strip()

        # Check each category's keywords
        for category, template_data in response_templates.items():
            if not isinstance(template_data, dict):
                continue
            keywords = template_data.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    logger.info(f"Response classified as '{category}' via keyword '{keyword}'")
                    return category

        return "other"

    async def classify_response_with_llm(
        self, message_text: str, response_templates: dict
    ) -> str:
        """Classify a response using LLM when keyword matching returns 'other'.

        Falls back to 'other' if LLM fails.
        """
        categories = list(response_templates.keys())
        categories_str = ", ".join(categories)

        prompt = (
            f"Classify this customer SMS response into exactly one category.\n\n"
            f"Categories: {categories_str}\n\n"
            f"Category descriptions:\n"
            f"- price: asking about cost, fees, pricing\n"
            f"- spouse: needs to check with partner/spouse before deciding\n"
            f"- schedule: asking about class times, adding another day, twice a week\n"
            f"- sibling: asking about enrolling multiple children\n"
            f"- yes_link: ready to proceed, wants the registration link\n"
            f"- not_interested: wants to stop, not interested, unsubscribe\n"
            f"- other: doesn't fit any category above\n\n"
            f"Customer message: \"{message_text}\"\n\n"
            f"Respond with ONLY the category name, nothing else."
        )

        try:
            result = await self.llm_orchestrator.generate(prompt)
            category = result.strip().lower().replace('"', "").replace("'", "")
            if category in categories:
                logger.info(f"LLM classified response as '{category}'")
                return category
            logger.warning(f"LLM returned invalid category '{category}', using 'other'")
            return "other"
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return "other"

    async def _get_org_id(self, tenant_id: int) -> str | None:
        """Get Jackrabbit org_id for a tenant from customer service config."""
        try:
            from app.persistence.database import async_session_factory
            from sqlalchemy import select
            from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig

            async with async_session_factory() as session:
                stmt = select(TenantCustomerServiceConfig).where(
                    TenantCustomerServiceConfig.tenant_id == tenant_id
                )
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()
                if config and hasattr(config, "jackrabbit_org_id"):
                    return config.jackrabbit_org_id
                return None
        except Exception as e:
            logger.error(f"Failed to get org_id for tenant {tenant_id}: {e}")
            return None
