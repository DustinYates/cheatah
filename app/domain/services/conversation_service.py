"""Conversation service for managing conversations and messages."""

import logging
import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

# In-memory cooldown: {(tenant_id, conversation_id): last_notified_timestamp}
# Prevents notification spam — one notification per conversation per 60 seconds
_notification_cooldowns: dict[tuple[int, int], float] = {}
_COOLDOWN_SECONDS = 60


class ConversationService:
    """Service for conversation and message management."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize conversation service."""
        self.session = session
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)

    async def create_conversation(
        self, tenant_id: int, channel: str, external_id: str | None = None
    ) -> Conversation:
        """Create a new conversation.

        Args:
            tenant_id: Tenant ID
            channel: Channel type (web, sms, voice)
            external_id: Optional external ID for idempotency

        Returns:
            Created conversation
        """
        if external_id:
            existing = await self.conversation_repo.get_by_external_id(
                tenant_id, external_id
            )
            if existing:
                return existing

        try:
            conversation = await self.conversation_repo.create(
                tenant_id,
                channel=channel,
                external_id=external_id,
            )
            return conversation
        except IntegrityError:
            # Unique index violation — another concurrent request created it first
            await self.session.rollback()
            if external_id:
                existing = await self.conversation_repo.get_by_external_id(
                    tenant_id, external_id
                )
                if existing:
                    logger.info(
                        f"Resolved concurrent conversation creation for external_id={external_id}"
                    )
                    return existing
            raise

    async def add_message(
        self, tenant_id: int, conversation_id: int, role: str, content: str,
        metadata: dict | None = None,
    ) -> Message:
        """Add a message to a conversation.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional JSON metadata for the message

        Returns:
            Created message

        Raises:
            ValueError: If conversation not found
        """
        conversation = await self.conversation_repo.get_by_id(tenant_id, conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        sequence_number = await self.message_repo.get_next_sequence_number(
            tenant_id, conversation_id
        )

        create_kwargs = dict(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sequence_number=sequence_number,
        )
        if metadata is not None:
            create_kwargs["message_metadata"] = metadata

        message = await self.message_repo.create(
            None,  # Messages inherit tenant_id from their Conversation
            **create_kwargs,
        )

        # Fire in-app notification for inbound user messages
        if role == "user":
            await self._maybe_notify_new_message(
                tenant_id=tenant_id,
                conversation=conversation,
                content=content,
            )

        return message

    async def get_conversation_history(
        self, tenant_id: int, conversation_id: int
    ) -> list[Message]:
        """Get conversation history in chronological order.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            List of messages ordered by sequence_number
        """
        return await self.message_repo.get_by_conversation(tenant_id, conversation_id)

    async def get_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Conversation | None:
        """Get a conversation by ID with messages loaded.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Conversation with messages or None if not found
        """
        return await self.conversation_repo.get_by_id_with_messages(tenant_id, conversation_id)

    async def _maybe_notify_new_message(
        self,
        tenant_id: int,
        conversation: Conversation,
        content: str,
    ) -> None:
        """Fire an in-app notification for a new user message, with cooldown."""
        try:
            # Skip resolved conversations
            if getattr(conversation, "status", None) == "resolved":
                return

            # Cooldown check — one notification per conversation per 60s
            key = (tenant_id, conversation.id)
            now = time.monotonic()
            last = _notification_cooldowns.get(key, 0)
            if now - last < _COOLDOWN_SECONDS:
                return
            _notification_cooldowns[key] = now

            # Resolve sender info from contact if available
            sender_name = None
            sender_phone = conversation.phone_number
            if conversation.contact_id:
                from app.persistence.repositories.contact_repository import ContactRepository
                contact_repo = ContactRepository(self.session)
                contact = await contact_repo.get_by_id(tenant_id, conversation.contact_id)
                if contact:
                    sender_name = contact.name
                    sender_phone = sender_phone or contact.phone

            from app.infrastructure.notifications import NotificationService
            notif_service = NotificationService(self.session)
            await notif_service.notify_new_message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                channel=conversation.channel or "web",
                sender_name=sender_name,
                sender_phone=sender_phone,
                message_preview=content,
            )
        except Exception as e:
            logger.warning(f"Failed to create new-message notification: {e}", exc_info=True)
