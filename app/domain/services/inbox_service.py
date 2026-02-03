"""Inbox service for unified conversation management."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.services.conversation_service import ConversationService
from app.domain.services.escalation_service import EscalationService
from app.infrastructure.telephony.factory import TelephonyProviderFactory
from app.persistence.models.conversation import Conversation
from app.persistence.models.escalation import Escalation
from app.persistence.repositories.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


class InboxService:
    """Service for inbox operations: listing, replying, and managing conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversation_repo = ConversationRepository(session)
        self.conversation_service = ConversationService(session)

    async def list_conversations(
        self,
        tenant_id: int,
        channel: str | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """List conversations for the inbox with enriched data.

        Args:
            tenant_id: Tenant ID
            channel: Optional channel filter
            status: Optional status filter
            search: Optional search text
            skip: Pagination offset
            limit: Page size

        Returns:
            Dict with conversations list and total count
        """
        conversations = await self.conversation_repo.list_for_inbox(
            tenant_id=tenant_id,
            channel=channel,
            status=status,
            search=search,
            skip=skip,
            limit=limit,
        )
        total = await self.conversation_repo.count_for_inbox(
            tenant_id=tenant_id,
            channel=channel,
            status=status,
            search=search,
        )
        return {"conversations": conversations, "total": total}

    async def get_conversation_detail(
        self, tenant_id: int, conversation_id: int
    ) -> dict | None:
        """Get full conversation detail with messages, contact info, and escalations.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Dict with conversation detail or None if not found
        """
        conv = await self.conversation_repo.get_by_id_with_messages(
            tenant_id, conversation_id
        )
        if not conv:
            return None

        # Get contact info
        contact = None
        if conv.contact_id:
            from app.persistence.models.contact import Contact

            stmt = select(Contact).where(
                Contact.id == conv.contact_id,
                Contact.deleted_at.is_(None),
            )
            result = await self.session.execute(stmt)
            contact_obj = result.scalar_one_or_none()
            if contact_obj:
                contact = {
                    "id": contact_obj.id,
                    "name": contact_obj.name,
                    "phone": contact_obj.phone,
                    "email": contact_obj.email,
                }

        # Get escalations for this conversation
        stmt = (
            select(Escalation)
            .where(
                Escalation.tenant_id == tenant_id,
                Escalation.conversation_id == conversation_id,
            )
            .order_by(Escalation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        escalations = [
            {
                "id": esc.id,
                "reason": esc.reason,
                "status": esc.status,
                "trigger_message": esc.trigger_message,
                "created_at": esc.created_at.isoformat() if esc.created_at else None,
                "resolved_at": esc.resolved_at.isoformat() if esc.resolved_at else None,
                "resolution_notes": esc.resolution_notes,
            }
            for esc in result.scalars().all()
        ]

        messages = [
            {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "role": msg.role,
                "content": msg.content,
                "sequence_number": msg.sequence_number,
                "metadata": msg.message_metadata,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in (conv.messages or [])
        ]

        return {
            "id": conv.id,
            "tenant_id": conv.tenant_id,
            "channel": conv.channel,
            "status": conv.status,
            "phone_number": conv.phone_number,
            "contact": contact,
            "messages": messages,
            "escalations": escalations,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        }

    async def reply_to_conversation(
        self,
        tenant_id: int,
        conversation_id: int,
        content: str,
        user_id: int,
    ) -> dict:
        """Send a human reply to a conversation.

        For SMS: sends via TelephonyProviderFactory and records the message.
        For web chat: records the message only (widget polls for new messages).
        Voice and email are read-only.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            content: Reply message text
            user_id: ID of the user sending the reply

        Returns:
            Dict with created message info

        Raises:
            ValueError: If conversation not found or channel doesn't support replies
        """
        conv = await self.conversation_repo.get_by_id_with_messages(
            tenant_id, conversation_id
        )
        if not conv:
            raise ValueError("Conversation not found")

        if conv.channel not in ("sms", "web"):
            raise ValueError(f"Cannot reply to {conv.channel} conversations. Only SMS and web chat support replies.")

        metadata = {"human_reply": True, "sent_by": user_id}

        # For SMS, send the message via telephony provider
        if conv.channel == "sms":
            if not conv.phone_number:
                raise ValueError("SMS conversation has no phone number")

            factory = TelephonyProviderFactory(self.session)
            sms_provider = await factory.get_sms_provider(tenant_id)
            if not sms_provider:
                raise ValueError("SMS provider not configured for this tenant")

            config = await factory.get_config(tenant_id)
            from_number = factory.get_sms_phone_number(config)
            if not from_number:
                raise ValueError("SMS phone number not configured for this tenant")

            send_result = await sms_provider.send_sms(
                to=conv.phone_number,
                from_=from_number,
                body=content,
            )
            metadata["provider_message_id"] = send_result.message_id
            metadata["provider"] = send_result.provider
            logger.info(
                "Inbox human reply sent via SMS: tenant=%d conv=%d to=%s",
                tenant_id, conversation_id, conv.phone_number,
            )

        # Record the message in the conversation
        message = await self.conversation_service.add_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata=metadata,
        )

        # Update conversation timestamp
        conv.updated_at = datetime.utcnow()
        await self.session.commit()

        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "sequence_number": message.sequence_number,
            "metadata": message.message_metadata,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    async def resolve_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> dict:
        """Set conversation status to 'resolved'.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Dict with updated status

        Raises:
            ValueError: If conversation not found
        """
        conv = await self._get_conversation(tenant_id, conversation_id)
        conv.status = "resolved"
        conv.updated_at = datetime.utcnow()
        await self.session.commit()
        return {"id": conv.id, "status": conv.status}

    async def reopen_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> dict:
        """Set conversation status back to 'open'.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Dict with updated status

        Raises:
            ValueError: If conversation not found
        """
        conv = await self._get_conversation(tenant_id, conversation_id)
        conv.status = "open"
        conv.updated_at = datetime.utcnow()
        await self.session.commit()
        return {"id": conv.id, "status": conv.status}

    async def resolve_escalation(
        self,
        tenant_id: int,
        escalation_id: int,
        user_id: int,
        notes: str | None = None,
    ) -> dict:
        """Resolve a pending escalation.

        Args:
            tenant_id: Tenant ID
            escalation_id: Escalation ID
            user_id: ID of the user resolving
            notes: Optional resolution notes

        Returns:
            Dict with escalation status

        Raises:
            ValueError: If escalation not found
        """
        escalation_service = EscalationService(self.session)
        escalation = await escalation_service.resolve_escalation(
            tenant_id=tenant_id,
            escalation_id=escalation_id,
            resolved_by=user_id,
            resolution_notes=notes,
        )
        if not escalation:
            raise ValueError("Escalation not found")
        return {
            "id": escalation.id,
            "status": escalation.status,
            "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
        }

    async def _get_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Conversation:
        """Get conversation or raise ValueError."""
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.id == conversation_id,
        )
        result = await self.session.execute(stmt)
        conv = result.scalar_one_or_none()
        if not conv:
            raise ValueError("Conversation not found")
        return conv
