"""Conversation and Message models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.contact import Contact
    from app.persistence.models.escalation import Escalation
    from app.persistence.models.lead import Lead
    from app.persistence.models.tenant import Tenant


class Conversation(Base):
    """Conversation model representing a customer interaction."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # web, sms, voice
    external_id = Column(String(255), nullable=True, index=True)  # For idempotency
    phone_number = Column(String(50), nullable=True, index=True)  # For SMS conversations
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    source_conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Customer Happiness Index (computed by CHI worker)
    chi_score = Column(Float, nullable=True, index=True)  # 0-100
    chi_computed_at = Column(DateTime, nullable=True)
    chi_signals = Column(JSON, nullable=True)  # Signal breakdown for explainability

    # Topic classification (computed by topic worker)
    topic = Column(String(50), nullable=True, index=True)

    # Inbox status
    status = Column(String(20), nullable=False, default="open", index=True)  # open, resolved

    # Relationships
    tenant = relationship("Tenant", back_populates="conversations")
    contact = relationship("Contact", back_populates="conversations")
    source_conversation = relationship("Conversation", remote_side="Conversation.id", foreign_keys=[source_conversation_id])
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.sequence_number"
    )
    leads = relationship("Lead", back_populates="conversation")
    escalations = relationship("Escalation", back_populates="conversation")
    email_conversations = relationship("EmailConversation", back_populates="conversation")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, tenant_id={self.tenant_id}, channel={self.channel})>"


class Message(Base):
    """Message model representing individual messages in a conversation."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    sequence_number = Column(Integer, nullable=False, index=True)
    message_metadata = Column("metadata", JSON, nullable=True)  # For audit trail (Twilio SID, delivery status, etc.)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, role={self.role}, sequence={self.sequence_number})>"

