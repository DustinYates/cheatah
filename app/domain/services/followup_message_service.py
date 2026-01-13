"""Service for composing LLM-generated follow-up messages."""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.prompt_service import PromptService
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.conversation import Conversation
from app.persistence.models.lead import Lead
from app.persistence.repositories.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


class FollowUpMessageService:
    """Service for composing LLM-generated follow-up messages."""

    MAX_SMS_LENGTH = 160

    def __init__(self, session: AsyncSession) -> None:
        """Initialize follow-up message service."""
        self.session = session
        self.prompt_service = PromptService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.conversation_repo = ConversationRepository(session)

    async def compose_followup_message(
        self,
        tenant_id: int,
        lead: Lead,
    ) -> str:
        """Compose an LLM-generated follow-up SMS message.

        Args:
            tenant_id: Tenant ID
            lead: Lead to follow up with

        Returns:
            Composed SMS message (max 160 chars)
        """
        # 1. Get original conversation if exists
        conversation = None
        conversation_summary = None
        if lead.conversation_id:
            try:
                conversation = await self.conversation_repo.get_by_id_with_messages(
                    tenant_id, lead.conversation_id
                )
                if conversation and conversation.messages:
                    conversation_summary = self._summarize_conversation(conversation)
            except Exception as e:
                logger.warning(f"Failed to fetch conversation for lead {lead.id}: {e}")

        # 2. Build context for LLM
        lead_source = lead.extra_data.get("source") if lead.extra_data else "contact"
        lead_name = lead.name or ""
        first_name = lead_name.split()[0] if lead_name else ""

        time_since_contact = self._get_time_since_contact(lead.created_at)

        context = {
            "lead_name": lead_name,
            "first_name": first_name,
            "lead_source": lead_source,
            "time_since_contact": time_since_contact,
            "conversation_summary": conversation_summary,
        }

        # 3. Get follow-up prompt
        system_prompt = await self.prompt_service.compose_prompt_sms_followup(
            tenant_id, context
        )

        if not system_prompt:
            # Fallback to template if no prompt configured
            logger.warning(f"No prompt configured for tenant {tenant_id}, using fallback")
            return self._generate_fallback_message(lead, lead_source)

        # 4. Build the full prompt for generation
        full_prompt = self._build_followup_prompt(system_prompt, context)

        # 5. Generate message via LLM
        try:
            response = await self.llm_orchestrator.generate(full_prompt)
            message = self._format_sms_response(response)
            logger.info(f"LLM-generated follow-up for lead {lead.id}: {len(message)} chars")
            return message
        except Exception as e:
            logger.error(f"LLM generation failed for follow-up to lead {lead.id}: {e}")
            return self._generate_fallback_message(lead, lead_source)

    def _summarize_conversation(self, conversation: Conversation) -> str:
        """Create a brief summary of the conversation for context."""
        messages = conversation.messages or []
        user_messages = [m.content for m in messages if m.role == "user"]

        if not user_messages:
            return "No previous messages from user."

        # Take first user message for context (truncate if too long)
        summary_parts = []
        if user_messages:
            first_msg = user_messages[0][:150] if len(user_messages[0]) > 150 else user_messages[0]
            summary_parts.append(f"Initial inquiry: {first_msg}")

        if len(user_messages) > 1:
            last_msg = user_messages[-1][:100] if len(user_messages[-1]) > 100 else user_messages[-1]
            summary_parts.append(f"Last message: {last_msg}")

        return " | ".join(summary_parts)

    def _get_time_since_contact(self, created_at: datetime | None) -> str:
        """Get human-readable time since original contact."""
        if not created_at:
            return "recently"

        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        delta = now - created_at
        hours = delta.total_seconds() / 3600

        if hours < 1:
            return "just now"
        elif hours < 24:
            return f"{int(hours)} hour{'s' if int(hours) > 1 else ''} ago"
        else:
            days = int(hours / 24)
            return f"{days} day{'s' if days > 1 else ''} ago"

    def _build_followup_prompt(self, system_prompt: str, context: dict) -> str:
        """Build the full prompt for LLM follow-up message generation."""
        prompt_parts = [system_prompt]

        prompt_parts.append("\n\nFOLLOW-UP CONTEXT:")
        prompt_parts.append(f"- Lead name: {context.get('first_name') or 'Unknown'}")
        prompt_parts.append(f"- How they contacted us: {context.get('lead_source', 'unknown')}")
        prompt_parts.append(f"- Time since contact: {context.get('time_since_contact', 'recently')}")

        if context.get("conversation_summary"):
            prompt_parts.append(f"- Previous conversation: {context['conversation_summary']}")

        prompt_parts.append(
            "\n\nGenerate a follow-up SMS message. Output ONLY the message text, nothing else:"
        )

        return "\n".join(prompt_parts)

    def _format_sms_response(self, response: str) -> str:
        """Format LLM response for SMS constraints."""
        # Remove markdown formatting
        response = re.sub(r"\*\*(.+?)\*\*", r"\1", response)
        response = re.sub(r"\*(.+?)\*", r"\1", response)
        response = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", response)
        response = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", response)
        response = re.sub(r"(?m)^\s*[-*+]\s+", "", response)
        response = re.sub(r"(?m)^\s*\d+\.\s+", "", response)

        # Remove any quotes that might wrap the message
        response = response.strip().strip('"').strip("'")

        # Clean up whitespace
        response = response.replace("*", "")
        response = response.replace("_", "")
        response = response.replace("`", "")
        response = " ".join(response.split())

        # Truncate if too long
        if len(response) > self.MAX_SMS_LENGTH:
            # Try to truncate at a word boundary
            truncated = response[: self.MAX_SMS_LENGTH - 3]
            last_space = truncated.rfind(" ")
            if last_space > self.MAX_SMS_LENGTH - 30:
                truncated = truncated[:last_space]
            response = truncated + "..."

        return response

    def _generate_fallback_message(self, lead: Lead, source: str) -> str:
        """Generate template-based fallback message."""
        first_name = (lead.name or "").split()[0] if lead.name else ""

        if source == "voice_call":
            if first_name:
                return f"Hi {first_name}! Thanks for calling earlier. How can I help you today?"
            return "Hi! Thanks for calling earlier. How can I help you today?"
        elif source == "email":
            if first_name:
                return f"Hi {first_name}! Thanks for filling out a form on our website. How can I help?"
            return "Hi! Thanks for filling out a form on our website. How can I help?"
        else:
            if first_name:
                return f"Hi {first_name}! Following up on your inquiry. How can I help?"
            return "Hi! Following up on your inquiry. How can I help?"
