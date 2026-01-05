"""Conversation service for managing conversations and messages."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.message_repository import MessageRepository


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

        conversation = await self.conversation_repo.create(
            tenant_id,
            channel=channel,
            external_id=external_id,
        )
        return conversation

    async def add_message(
        self, tenant_id: int, conversation_id: int, role: str, content: str
    ) -> Message:
        """Add a message to a conversation.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            role: Message role (user, assistant, system)
            content: Message content

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

        message = await self.message_repo.create(
            tenant_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            sequence_number=sequence_number,
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
