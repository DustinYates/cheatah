"""Service for handing off web chat conversations to SMS."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.lead import Lead
from app.persistence.models.tenant import TenantBusinessProfile
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.lead_repository import LeadRepository

logger = logging.getLogger(__name__)


@dataclass
class HandoffResult:
    """Result of a chat-to-SMS handoff."""

    status: str  # "sent", "failed", "skipped"
    sms_conversation_id: int | None = None
    error: str | None = None


class ChatSmsHandoffService:
    """Orchestrates handing off a web chat conversation to SMS."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.lead_repo = LeadRepository(session)

    @staticmethod
    def _normalize_phone(phone: str) -> str | None:
        """Normalize phone number to E.164 format."""
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            digits = "1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        if phone.startswith("+") and len(digits) >= 10:
            return f"+{digits}"
        return None

    async def initiate_handoff(
        self,
        tenant_id: int,
        chat_conversation_id: int,
        phone: str,
        customer_name: str | None = None,
    ) -> HandoffResult:
        """Send initial SMS and create linked SMS conversation.

        Args:
            tenant_id: Tenant ID
            chat_conversation_id: Source web chat conversation ID
            phone: Customer phone number
            customer_name: Customer name (optional)

        Returns:
            HandoffResult with status and SMS conversation ID
        """
        try:
            phone = self._normalize_phone(phone)
            if not phone:
                return HandoffResult(status="failed", error="Invalid phone number")

            # Check if an SMS conversation already exists for this phone
            existing_sms = await self.conv_repo.get_by_phone_number(
                tenant_id, phone, channel="sms"
            )

            if existing_sms and existing_sms.source_conversation_id == chat_conversation_id:
                logger.info(
                    f"Handoff already done for chat {chat_conversation_id} -> SMS {existing_sms.id}"
                )
                return HandoffResult(status="skipped", sms_conversation_id=existing_sms.id)

            if existing_sms:
                # Reuse existing SMS conversation, update source link
                sms_conversation = existing_sms
                sms_conversation.source_conversation_id = chat_conversation_id
            else:
                # Create new SMS conversation linked to the chat
                sms_conversation = Conversation(
                    tenant_id=tenant_id,
                    channel="sms",
                    phone_number=phone,
                    source_conversation_id=chat_conversation_id,
                )
                # Copy contact_id from chat conversation
                chat_conv = await self.conv_repo.get_by_id(tenant_id, chat_conversation_id)
                if chat_conv and chat_conv.contact_id:
                    sms_conversation.contact_id = chat_conv.contact_id

                self.session.add(sms_conversation)

            await self.session.commit()
            await self.session.refresh(sms_conversation)

            # Build context summary from chat messages and store as system message
            context_summary = await self._build_chat_summary(chat_conversation_id)
            if context_summary:
                max_seq_stmt = select(func.max(Message.sequence_number)).where(
                    Message.conversation_id == sms_conversation.id
                )
                max_seq_result = await self.session.execute(max_seq_stmt)
                max_seq = max_seq_result.scalar() or 0

                system_msg = Message(
                    conversation_id=sms_conversation.id,
                    role="system",
                    content=context_summary,
                    sequence_number=max_seq + 1,
                    message_metadata={
                        "handoff_context": True,
                        "source_conversation_id": chat_conversation_id,
                    },
                )
                self.session.add(system_msg)
                await self.session.commit()

            # Send initial SMS
            greeting = await self._build_greeting(tenant_id, customer_name)
            sms_sent = await self._send_sms(tenant_id, phone, greeting)

            if not sms_sent:
                return HandoffResult(
                    status="failed",
                    sms_conversation_id=sms_conversation.id,
                    error="SMS send failed",
                )

            # Record the outbound message
            max_seq_stmt = select(func.max(Message.sequence_number)).where(
                Message.conversation_id == sms_conversation.id
            )
            max_seq_result = await self.session.execute(max_seq_stmt)
            max_seq = max_seq_result.scalar() or 0

            outbound_msg = Message(
                conversation_id=sms_conversation.id,
                role="assistant",
                content=greeting,
                sequence_number=max_seq + 1,
            )
            self.session.add(outbound_msg)

            # Update lead with handoff metadata
            await self._update_lead_handoff(
                tenant_id, chat_conversation_id, sms_conversation.id
            )

            await self.session.commit()

            logger.info(
                f"Chat-to-SMS handoff completed - tenant_id={tenant_id}, "
                f"chat_conv={chat_conversation_id}, sms_conv={sms_conversation.id}, "
                f"phone={phone}"
            )

            return HandoffResult(status="sent", sms_conversation_id=sms_conversation.id)

        except Exception as e:
            logger.error(
                f"Chat-to-SMS handoff failed - tenant_id={tenant_id}, "
                f"chat_conv={chat_conversation_id}, error={e}",
                exc_info=True,
            )
            return HandoffResult(status="failed", error=str(e))

    async def _build_chat_summary(self, chat_conversation_id: int) -> str | None:
        """Build a summary of the chat conversation for SMS context."""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == chat_conversation_id,
                Message.role.in_(["user", "assistant"]),
            )
            .order_by(Message.sequence_number.desc())
            .limit(10)
        )
        result = await self.session.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        if not messages:
            return None

        parts = ["PREVIOUS WEB CHAT CONTEXT (continue this conversation naturally):"]
        for msg in messages:
            role_label = "Customer" if msg.role == "user" else "Agent"
            # Truncate long messages for SMS context
            content = msg.content[:300] if len(msg.content) > 300 else msg.content
            parts.append(f"{role_label}: {content}")

        return "\n".join(parts)

    async def _build_greeting(self, tenant_id: int, customer_name: str | None) -> str:
        """Build the initial handoff SMS greeting."""
        # Get business name
        stmt = select(TenantBusinessProfile).where(
            TenantBusinessProfile.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()
        business_name = profile.business_name if profile else "us"

        return (
            f"Hi! This is {business_name} following up from our chat. "
            f"Feel free to continue the conversation here via text!"
        )

    async def _send_sms(self, tenant_id: int, phone: str, message: str) -> bool:
        """Send SMS via the tenant's configured provider."""
        try:
            factory = TelephonyProviderFactory(self.session)
            sms_provider = await factory.get_sms_provider(tenant_id)
            if not sms_provider:
                logger.error(f"No SMS provider for tenant {tenant_id}")
                return False

            from app.persistence.models.tenant_sms_config import TenantSmsConfig

            sms_config_stmt = select(TenantSmsConfig).where(
                TenantSmsConfig.tenant_id == tenant_id
            )
            sms_config_result = await self.session.execute(sms_config_stmt)
            sms_config = sms_config_result.scalar_one_or_none()
            if not sms_config:
                logger.error(f"No SMS config for tenant {tenant_id}")
                return False

            from_number = factory.get_sms_phone_number(sms_config)
            if not from_number:
                logger.error(f"No SMS from number for tenant {tenant_id}")
                return False

            send_result = await sms_provider.send_sms(
                to=phone,
                from_=from_number,
                body=message,
                status_callback=None,
            )
            return bool(send_result and send_result.message_id)

        except Exception as e:
            logger.error(f"Failed to send handoff SMS: {e}", exc_info=True)
            return False

    async def _update_lead_handoff(
        self,
        tenant_id: int,
        chat_conversation_id: int,
        sms_conversation_id: int,
    ) -> None:
        """Update lead extra_data with handoff metadata."""
        try:
            lead = await self.lead_repo.get_by_conversation(
                tenant_id, chat_conversation_id
            )
            if not lead:
                return

            extra_data = lead.extra_data or {}
            extra_data["handoff"] = {
                "from_channel": "web",
                "from_conversation_id": chat_conversation_id,
                "to_channel": "sms",
                "to_conversation_id": sms_conversation_id,
                "handoff_at": datetime.utcnow().isoformat(),
            }
            extra_data.setdefault("linked_conversations", [])
            if sms_conversation_id not in extra_data["linked_conversations"]:
                extra_data["linked_conversations"].append(sms_conversation_id)

            lead.extra_data = extra_data
            lead.updated_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Failed to update lead handoff metadata: {e}", exc_info=True)
