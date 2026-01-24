"""Model for tracking sent assets (registration links, etc.) for deduplication."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint

from app.persistence.database import Base


class SentAsset(Base):
    """Tracks assets sent to phone numbers to prevent duplicate sends.

    This table provides database-level deduplication as a fallback when Redis
    is unavailable. The unique constraint ensures that even concurrent requests
    cannot create duplicate records.
    """

    __tablename__ = "sent_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    phone_normalized = Column(String(20), nullable=False, index=True)
    asset_type = Column(String(50), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    message_id = Column(String(100), nullable=True)
    conversation_id = Column(Integer, nullable=True)

    __table_args__ = (
        # Unique constraint prevents duplicate sends at database level
        UniqueConstraint(
            "tenant_id",
            "phone_normalized",
            "asset_type",
            name="uq_sent_assets_tenant_phone_asset",
        ),
        # Index for fast lookups
        Index("ix_sent_assets_lookup", "tenant_id", "phone_normalized", "asset_type"),
    )

    def __repr__(self) -> str:
        return (
            f"SentAsset(id={self.id}, tenant_id={self.tenant_id}, "
            f"phone={self.phone_normalized}, asset_type={self.asset_type})"
        )
