"""Conversation repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation entities."""

    def __init__(self, session: AsyncSession):
        """Initialize conversation repository."""
        super().__init__(Conversation, session)

    async def get_by_id_with_messages(
        self, tenant_id: int, conversation_id: int
    ) -> Conversation | None:
        """Get conversation by ID with messages eagerly loaded.
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            
        Returns:
            Conversation with messages or None if not found
        """
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self, tenant_id: int, external_id: str
    ) -> Conversation | None:
        """Get conversation by external_id (for idempotency)."""
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.external_id == external_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone_number(
        self, tenant_id: int, phone_number: str, channel: str = "sms"
    ) -> Conversation | None:
        """Get conversation by phone number and channel.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            channel: Channel type (default: "sms")
            
        Returns:
            Conversation or None if not found
        """
        stmt = select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.phone_number == phone_number,
            Conversation.channel == channel
        ).order_by(Conversation.updated_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_channel(
        self, tenant_id: int, channel: str, skip: int = 0, limit: int = 100
    ) -> list[Conversation]:
        """List conversations by channel.
        
        Args:
            tenant_id: Tenant ID
            channel: Channel type
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of conversations
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.channel == channel
            )
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Conversation]:
        """List all conversations for tenant, ordered by updated_at.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of conversations
        """
        stmt = (
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_inbox(
        self,
        tenant_id: int,
        channel: str | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """List conversations for inbox with contact info, last message, and escalation count.

        Uses raw SQL with LATERAL joins for efficient single-query fetching.

        Args:
            tenant_id: Tenant ID
            channel: Optional channel filter (web, sms, voice)
            status: Optional status filter (open, resolved)
            search: Optional search text (matches contact name/phone/email or conversation phone)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of dicts with conversation + contact + last message + escalation info
        """
        params: dict = {
            "tenant_id": tenant_id,
            "skip": skip,
            "limit": limit,
        }

        where_clauses = ["c.tenant_id = :tenant_id"]

        if channel:
            where_clauses.append("c.channel = :channel")
            params["channel"] = channel

        if status:
            where_clauses.append("c.status = :status")
            params["status"] = status

        if search:
            where_clauses.append(
                "(ct.name ILIKE :search_pattern "
                "OR ct.phone ILIKE :search_pattern "
                "OR ct.email ILIKE :search_pattern "
                "OR c.phone_number ILIKE :search_pattern)"
            )
            params["search_pattern"] = f"%{search}%"

        where_sql = " AND ".join(where_clauses)

        query = text(f"""
            SELECT
                c.id, c.tenant_id, c.channel, c.phone_number, c.status,
                c.contact_id, c.created_at, c.updated_at,
                ct.name AS contact_name, ct.phone AS contact_phone, ct.email AS contact_email,
                lm.content AS last_message_content, lm.role AS last_message_role,
                lm.created_at AS last_message_at,
                COALESCE(esc.pending_count, 0) AS pending_escalations
            FROM conversations c
            LEFT JOIN contacts ct ON c.contact_id = ct.id AND ct.deleted_at IS NULL
            LEFT JOIN LATERAL (
                SELECT m.content, m.role, m.created_at
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.sequence_number DESC LIMIT 1
            ) lm ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS pending_count
                FROM escalations e
                WHERE e.conversation_id = c.id AND e.status IN ('pending', 'notified')
            ) esc ON TRUE
            WHERE {where_sql}
            ORDER BY c.updated_at DESC
            OFFSET :skip LIMIT :limit
        """)

        result = await self.session.execute(query, params)
        rows = result.mappings().all()
        return [dict(row) for row in rows]

    async def count_for_inbox(
        self,
        tenant_id: int,
        channel: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        """Count conversations for inbox with the same filters as list_for_inbox.

        Args:
            tenant_id: Tenant ID
            channel: Optional channel filter
            status: Optional status filter
            search: Optional search text

        Returns:
            Total count of matching conversations
        """
        params: dict = {"tenant_id": tenant_id}
        where_clauses = ["c.tenant_id = :tenant_id"]

        if channel:
            where_clauses.append("c.channel = :channel")
            params["channel"] = channel

        if status:
            where_clauses.append("c.status = :status")
            params["status"] = status

        if search:
            where_clauses.append(
                "(ct.name ILIKE :search_pattern "
                "OR ct.phone ILIKE :search_pattern "
                "OR ct.email ILIKE :search_pattern "
                "OR c.phone_number ILIKE :search_pattern)"
            )
            params["search_pattern"] = f"%{search}%"

        where_sql = " AND ".join(where_clauses)

        query = text(f"""
            SELECT COUNT(*)
            FROM conversations c
            LEFT JOIN contacts ct ON c.contact_id = ct.id AND ct.deleted_at IS NULL
            WHERE {where_sql}
        """)

        result = await self.session.execute(query, params)
        return result.scalar() or 0
