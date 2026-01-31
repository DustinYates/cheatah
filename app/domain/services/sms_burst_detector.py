"""SMS burst/spam detection service.

Detects repeated outbound SMS to the same recipient within a short time window.
Uses Redis for fast-path tracking with database fallback.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.redis import redis_client
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.sms_burst_config import SmsBurstConfig
from app.persistence.models.sms_burst_incident import SmsBurstIncident

logger = logging.getLogger(__name__)

# System defaults (used when no per-tenant config exists)
DEFAULT_TIME_WINDOW_SECONDS = 180
DEFAULT_MESSAGE_THRESHOLD = 3
DEFAULT_HIGH_SEVERITY_THRESHOLD = 5
DEFAULT_RAPID_GAP_MIN = 5
DEFAULT_RAPID_GAP_MAX = 29
DEFAULT_IDENTICAL_CONTENT_THRESHOLD = 2
DEFAULT_SIMILARITY_THRESHOLD = 0.9
DEFAULT_AUTO_BLOCK_THRESHOLD = 10


@dataclass
class BurstConfig:
    """Resolved burst detection configuration (tenant override or defaults)."""

    enabled: bool = True
    time_window_seconds: int = DEFAULT_TIME_WINDOW_SECONDS
    message_threshold: int = DEFAULT_MESSAGE_THRESHOLD
    high_severity_threshold: int = DEFAULT_HIGH_SEVERITY_THRESHOLD
    rapid_gap_min_seconds: int = DEFAULT_RAPID_GAP_MIN
    rapid_gap_max_seconds: int = DEFAULT_RAPID_GAP_MAX
    identical_content_threshold: int = DEFAULT_IDENTICAL_CONTENT_THRESHOLD
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    auto_block_enabled: bool = False
    auto_block_threshold: int = DEFAULT_AUTO_BLOCK_THRESHOLD
    excluded_flows: list[str] = field(default_factory=list)


@dataclass
class BurstCheckResult:
    """Result of a burst detection check."""

    is_burst: bool = False
    severity: str = "warning"
    should_block: bool = False
    incident_id: int | None = None
    message_count: int = 0


def _content_hash(text: str) -> str:
    """Compute a short hash of message content for dedup comparison."""
    normalized = text.strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _compute_avg_gap(timestamps: list[float]) -> float:
    """Compute average gap in seconds between sorted timestamps."""
    if len(timestamps) < 2:
        return 0.0
    gaps = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    return sum(gaps) / len(gaps)


def _detect_identical_content(hashes: list[str]) -> tuple[bool, int]:
    """Check for repeated content hashes. Returns (has_identical, max_repeat_count)."""
    if not hashes:
        return False, 0
    counts: dict[str, int] = {}
    for h in hashes:
        counts[h] = counts.get(h, 0) + 1
    max_count = max(counts.values())
    return max_count >= 2, max_count


def _determine_likely_cause(avg_gap: float, count: int, has_identical: bool) -> str:
    """Heuristic root cause classification."""
    if avg_gap < 3:
        return "duplicate_webhook"
    if avg_gap < 15 and has_identical:
        return "task_retry"
    if count > 10:
        return "tool_loop"
    if 15 <= avg_gap <= 30:
        return "callback_confusion"
    return "unknown"


class SmsBurstDetector:
    """Detects SMS burst/spam patterns in real-time."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_outbound_sms(
        self,
        tenant_id: int,
        to_number: str,
        message_content: str,
        flow_type: str | None = None,
    ) -> BurstCheckResult:
        """Check if an outbound SMS triggers burst detection.

        Call this BEFORE sending each outbound SMS.

        Args:
            tenant_id: Tenant ID
            to_number: Recipient phone number (E.164)
            message_content: Message text being sent
            flow_type: Optional flow identifier (e.g. "otp", "opt_in") for exclusions

        Returns:
            BurstCheckResult indicating whether this is a burst and what action to take
        """
        config = await self._get_config(tenant_id)

        if not config.enabled:
            return BurstCheckResult()

        # Check exclusions
        if flow_type and flow_type in config.excluded_flows:
            return BurstCheckResult()

        now = time.time()
        content_h = _content_hash(message_content)

        # Try Redis fast path, fall back to DB
        if redis_client._enabled and redis_client._client is not None:
            return await self._check_via_redis(
                tenant_id, to_number, content_h, now, config
            )

        return await self._check_via_database(
            tenant_id, to_number, content_h, config
        )

    async def _get_config(self, tenant_id: int) -> BurstConfig:
        """Load tenant-specific config or return defaults."""
        try:
            stmt = select(SmsBurstConfig).where(SmsBurstConfig.tenant_id == tenant_id)
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                return BurstConfig()

            return BurstConfig(
                enabled=row.enabled,
                time_window_seconds=row.time_window_seconds,
                message_threshold=row.message_threshold,
                high_severity_threshold=row.high_severity_threshold,
                rapid_gap_min_seconds=row.rapid_gap_min_seconds,
                rapid_gap_max_seconds=row.rapid_gap_max_seconds,
                identical_content_threshold=row.identical_content_threshold,
                similarity_threshold=row.similarity_threshold,
                auto_block_enabled=row.auto_block_enabled,
                auto_block_threshold=row.auto_block_threshold,
                excluded_flows=row.excluded_flows or [],
            )
        except Exception as e:
            logger.warning(f"Failed to load burst config for tenant {tenant_id}: {e}")
            return BurstConfig()

    async def _check_via_redis(
        self,
        tenant_id: int,
        to_number: str,
        content_hash: str,
        now: float,
        config: BurstConfig,
    ) -> BurstCheckResult:
        """Redis-based burst tracking using a JSON list of recent sends."""
        key = f"sms_burst:{tenant_id}:{to_number}"
        try:
            # Get existing record
            data = await redis_client.get_json(key)
            entries: list[dict[str, Any]] = data.get("entries", []) if data else []

            # Add current send
            entries.append({"ts": now, "hash": content_hash})

            # Prune entries outside window
            cutoff = now - config.time_window_seconds
            entries = [e for e in entries if e["ts"] >= cutoff]

            # Save back
            await redis_client.set_json(key, {"entries": entries}, ttl=config.time_window_seconds)

            if len(entries) < config.message_threshold:
                return BurstCheckResult()

            # Burst detected — analyze
            timestamps = [e["ts"] for e in entries]
            hashes = [e["hash"] for e in entries]
            return await self._analyze_and_record(
                tenant_id, to_number, timestamps, hashes, config
            )
        except Exception as e:
            logger.warning(f"Redis burst check failed: {e}, falling back to DB")
            return await self._check_via_database(
                tenant_id, to_number, content_hash, config
            )

    async def _check_via_database(
        self,
        tenant_id: int,
        to_number: str,
        content_hash: str,
        config: BurstConfig,
    ) -> BurstCheckResult:
        """Database-based burst detection (fallback when Redis unavailable)."""
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=config.time_window_seconds)

            stmt = (
                select(Message.content, Message.created_at)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.channel == "sms",
                    Conversation.phone_number == to_number,
                    Message.role == "assistant",
                    Message.created_at >= cutoff,
                )
                .order_by(Message.created_at.asc())
                .limit(20)
            )

            result = await self.session.execute(stmt)
            rows = result.all()

            # +1 for the message we're about to send (not yet persisted)
            total_count = len(rows) + 1

            if total_count < config.message_threshold:
                return BurstCheckResult()

            timestamps = [r.created_at.timestamp() for r in rows]
            timestamps.append(datetime.utcnow().timestamp())
            hashes = [_content_hash(r.content) for r in rows]
            hashes.append(content_hash)

            return await self._analyze_and_record(
                tenant_id, to_number, timestamps, hashes, config
            )
        except Exception as e:
            logger.error(f"DB burst check failed: {e}", exc_info=True)
            return BurstCheckResult()

    async def _analyze_and_record(
        self,
        tenant_id: int,
        to_number: str,
        timestamps: list[float],
        hashes: list[str],
        config: BurstConfig,
    ) -> BurstCheckResult:
        """Analyze burst characteristics, determine severity, and create incident."""
        count = len(timestamps)
        avg_gap = _compute_avg_gap(sorted(timestamps))
        has_identical, identical_count = _detect_identical_content(hashes)

        # Determine severity
        severity = "warning"

        rapid_gap = (
            config.rapid_gap_min_seconds <= avg_gap <= config.rapid_gap_max_seconds
        )
        if rapid_gap:
            severity = "high"
        if has_identical and identical_count >= config.identical_content_threshold:
            severity = "high"
        if count >= config.high_severity_threshold:
            severity = "high"
        if count >= config.high_severity_threshold and has_identical and rapid_gap:
            severity = "critical"

        # Auto-block?
        should_block = (
            config.auto_block_enabled and count >= config.auto_block_threshold
        )

        likely_cause = _determine_likely_cause(avg_gap, count, has_identical)

        # Check for existing active incident for this tenant+number
        try:
            existing_stmt = (
                select(SmsBurstIncident)
                .where(
                    SmsBurstIncident.tenant_id == tenant_id,
                    SmsBurstIncident.to_number == to_number,
                    SmsBurstIncident.status == "active",
                )
                .order_by(SmsBurstIncident.detected_at.desc())
                .limit(1)
            )
            existing_result = await self.session.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()

            if existing:
                # Update existing incident
                existing.message_count = count
                existing.last_message_at = datetime.utcfromtimestamp(max(timestamps))
                existing.time_window_seconds = int(max(timestamps) - min(timestamps))
                existing.avg_gap_seconds = round(avg_gap, 2)
                existing.severity = severity
                existing.has_identical_content = has_identical
                existing.likely_cause = likely_cause
                if should_block:
                    existing.auto_blocked = True
                await self.session.commit()
                incident_id = existing.id
            else:
                # Create new incident
                incident = SmsBurstIncident(
                    tenant_id=tenant_id,
                    to_number=to_number,
                    message_count=count,
                    first_message_at=datetime.utcfromtimestamp(min(timestamps)),
                    last_message_at=datetime.utcfromtimestamp(max(timestamps)),
                    time_window_seconds=int(max(timestamps) - min(timestamps)),
                    avg_gap_seconds=round(avg_gap, 2),
                    severity=severity,
                    has_identical_content=has_identical,
                    content_similarity_score=1.0 if has_identical else None,
                    likely_cause=likely_cause,
                    handler="bot",
                    status="active",
                    auto_blocked=should_block,
                )
                self.session.add(incident)
                await self.session.commit()
                await self.session.refresh(incident)
                incident_id = incident.id

            logger.warning(
                f"SMS burst detected: tenant={tenant_id}, to={to_number}, "
                f"count={count}, avg_gap={avg_gap:.1f}s, severity={severity}, "
                f"cause={likely_cause}, incident_id={incident_id}, block={should_block}"
            )

            return BurstCheckResult(
                is_burst=True,
                severity=severity,
                should_block=should_block,
                incident_id=incident_id,
                message_count=count,
            )
        except Exception as e:
            logger.error(f"Failed to record burst incident: {e}", exc_info=True)
            # Still return burst detection result even if recording failed
            return BurstCheckResult(
                is_burst=True,
                severity=severity,
                should_block=should_block,
                message_count=count,
            )
