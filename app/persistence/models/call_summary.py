"""Call summary model for voice call summaries."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.persistence.database import Base

if TYPE_CHECKING:
    from app.persistence.models.call import Call
    from app.persistence.models.contact import Contact
    from app.persistence.models.lead import Lead


class CallSummary(Base):
    """Call summary model representing AI-generated summaries of voice calls."""

    __tablename__ = "call_summaries"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False, unique=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    
    # Intent classification
    intent = Column(String(50), nullable=True, index=True)
    # Values: pricing_info, hours_location, booking_request, support_request, wrong_number, general_inquiry
    
    # Call outcome
    outcome = Column(String(50), nullable=True, index=True)
    # Values: lead_created, info_provided, voicemail, booking_requested, transferred, dismissed
    
    # Summary content
    summary_text = Column(Text, nullable=True)

    # Full conversation transcript
    transcript = Column(Text, nullable=True)

    # Extracted structured data
    extracted_fields = Column(JSON, nullable=True)
    # Schema: {name, phone, email, reason, urgency, preferred_callback_time}
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    call = relationship("Call", back_populates="summary")
    contact = relationship("Contact", back_populates="call_summaries")
    lead = relationship("Lead", back_populates="call_summaries")

    def __repr__(self) -> str:
        return f"<CallSummary(id={self.id}, call_id={self.call_id}, intent={self.intent}, outcome={self.outcome})>"

