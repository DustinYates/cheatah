"""Builds a notes-and-history context blob for AI agents.

Aggregates per-lead and per-customer notes plus Jackrabbit account data
into a single text block suitable for stuffing into an LLM prompt or
returning to a Telnyx voice tool. Used so SMS / chat / voice agents have
the same operator-visible context the human team would have.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.customer import Customer
from app.persistence.models.lead import Lead
from app.persistence.models.lead_task import LeadTask
from app.persistence.repositories.customer_repository import CustomerRepository
from app.persistence.repositories.lead_repository import LeadRepository

logger = logging.getLogger(__name__)


class LeadContextService:
    """Aggregate notes + customer info for the agent's context window."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build_context(
        self,
        tenant_id: int,
        *,
        lead_id: int | None = None,
        phone: str | None = None,
        email: str | None = None,
    ) -> str | None:
        """Return a formatted notes blob, or None if nothing relevant exists.

        Lookup order: explicit lead_id > phone > email. Customer record is
        located by phone or email. All matched leads' notes and tasks are
        included so a returning customer who has multiple lead records
        doesn't lose history.
        """
        leads = await self._find_leads(tenant_id, lead_id, phone, email)
        customer = await self._find_customer(tenant_id, phone, email)

        if not leads and not customer:
            return None

        sections: list[str] = []

        if customer:
            sections.append(self._format_customer(customer))

        for lead in leads:
            section = await self._format_lead(lead)
            if section:
                sections.append(section)

        if not sections:
            return None

        header = "Customer history & notes (use this to personalize replies):"
        body = "\n\n".join(sections)
        return f"{header}\n{body}"

    # ── Lookups ──────────────────────────────────────────────────────────

    async def _find_leads(
        self,
        tenant_id: int,
        lead_id: int | None,
        phone: str | None,
        email: str | None,
    ) -> list[Lead]:
        repo = LeadRepository(self.session)

        if lead_id:
            lead = await repo.get_by_id(tenant_id, lead_id)
            return [lead] if lead else []

        if not phone and not email:
            return []

        # Reuse the existing email-or-phone lookup; it returns leads with
        # conversations attached, which is what we want for context.
        leads = await repo.find_leads_with_conversation_by_email_or_phone(
            tenant_id, email=email, phone=phone
        )
        if leads:
            return leads

        # Fallback: search by phone/email directly with no conversation join,
        # for leads captured via channels that don't auto-create conversations.
        stmt = select(Lead).where(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc()).limit(5)
        if phone:
            stmt = stmt.where(Lead.phone == phone)
        elif email:
            stmt = stmt.where(Lead.email == email)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _find_customer(
        self, tenant_id: int, phone: str | None, email: str | None
    ) -> Customer | None:
        repo = CustomerRepository(self.session)
        if phone:
            customer = await repo.get_by_phone(tenant_id, phone)
            if customer:
                return customer
        if email:
            customer = await repo.get_by_email(tenant_id, email)
            if customer:
                return customer
        return None

    # ── Formatters ───────────────────────────────────────────────────────

    def _format_customer(self, customer: Customer) -> str:
        lines = [f"## Existing customer record"]
        if customer.name:
            lines.append(f"- Name: {customer.name}")
        if customer.phone:
            lines.append(f"- Phone: {customer.phone}")
        if customer.email:
            lines.append(f"- Email: {customer.email}")
        if customer.status:
            lines.append(f"- Status: {customer.status}")
        if customer.external_customer_id:
            lines.append(f"- Jackrabbit ID: {customer.external_customer_id}")

        account_data = customer.account_data or {}
        if isinstance(account_data, dict) and account_data:
            interesting = self._summarize_account_data(account_data)
            if interesting:
                lines.append("- Account info:")
                for key, value in interesting:
                    lines.append(f"    - {key}: {value}")

        return "\n".join(lines)

    @staticmethod
    def _summarize_account_data(data: dict[str, Any]) -> list[tuple[str, str]]:
        """Pull a flat list of human-readable rows from account_data.

        Picks fields that are likely useful to the agent, skips noisy
        Jackrabbit internals (timestamps, _id fields, raw blobs).
        """
        skip_prefixes = ("_", "raw_", "internal_")
        skip_keys = {"id", "tenant_id", "created_at", "updated_at"}
        rows: list[tuple[str, str]] = []
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            if key in skip_keys or key.startswith(skip_prefixes):
                continue
            if value is None or value == "":
                continue
            if isinstance(value, (dict, list)):
                # Show top-level lists/dicts compactly
                rendered = str(value)
                if len(rendered) > 200:
                    rendered = rendered[:200] + "…"
                rows.append((key, rendered))
            else:
                rows.append((key, str(value)))
            if len(rows) >= 25:
                break
        return rows

    async def _format_lead(self, lead: Lead) -> str | None:
        # Skip leads that have nothing useful to add
        if not lead.notes and not lead.extra_data and not lead.custom_tags:
            tasks = await self._load_tasks(lead.id)
            if not tasks:
                return None
        else:
            tasks = await self._load_tasks(lead.id)

        lines = [f"## Lead #{lead.id}"]
        if lead.name:
            lines.append(f"- Name: {lead.name}")
        if lead.phone:
            lines.append(f"- Phone: {lead.phone}")
        if lead.email:
            lines.append(f"- Email: {lead.email}")
        if lead.pipeline_stage:
            lines.append(f"- Pipeline stage: {lead.pipeline_stage}")
        if lead.status and lead.status != lead.pipeline_stage:
            lines.append(f"- Status: {lead.status}")

        if lead.custom_tags:
            tag_str = ", ".join(t for t in lead.custom_tags if isinstance(t, str))
            if tag_str:
                lines.append(f"- Tags: {tag_str}")

        if lead.notes:
            lines.append("- Notes:")
            for line in str(lead.notes).strip().splitlines():
                if line.strip():
                    lines.append(f"    {line.strip()}")

        # Selected extra_data — surface what's most useful to the agent
        if lead.extra_data:
            interesting = self._summarize_extra_data(lead.extra_data)
            if interesting:
                lines.append("- Lead details:")
                for key, value in interesting:
                    lines.append(f"    - {key}: {value}")

        if tasks:
            lines.append("- Open tasks:")
            for task in tasks:
                due = f" (due {task.due_date.strftime('%Y-%m-%d')})" if task.due_date else ""
                lines.append(f"    - {task.title}{due}")

        if len(lines) == 1:
            return None
        return "\n".join(lines)

    async def _load_tasks(self, lead_id: int) -> list[LeadTask]:
        stmt = (
            select(LeadTask)
            .where(LeadTask.lead_id == lead_id, LeadTask.is_completed.is_(False))
            .order_by(LeadTask.due_date.is_(None), LeadTask.due_date)
            .limit(10)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def _summarize_extra_data(data: dict[str, Any]) -> list[tuple[str, str]]:
        """Pull human-readable rows from a lead's extra_data."""
        priority_keys = [
            "type of lessons", "class code", "location code",
            "ad title", "How did you hear about us?",
            "preferred_day", "preferred_time", "first_class_date",
            "child_name", "child_age", "experience_level",
            "source", "utm_source", "utm_campaign",
        ]
        rows: list[tuple[str, str]] = []
        seen: set[str] = set()
        for key in priority_keys:
            for actual_key in data.keys():
                if not isinstance(actual_key, str):
                    continue
                if actual_key.lower() == key.lower() and actual_key not in seen:
                    value = data[actual_key]
                    if value not in (None, "", [], {}):
                        rendered = str(value)
                        if len(rendered) > 160:
                            rendered = rendered[:160] + "…"
                        rows.append((actual_key, rendered))
                        seen.add(actual_key)
                        break
        return rows
