"""Telnyx sync monitor service.

Compares local DB records against the Telnyx API to detect missing
calls, missing SMS messages, and stale delivery statuses.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.telephony.telnyx_provider import TelnyxAIService, TelnyxSmsProvider
from app.persistence.models.call import Call
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.telnyx_sync_result import TelnyxSyncResult

logger = logging.getLogger(__name__)

# Max individual message status lookups per run (rate limit safety)
MAX_DELIVERY_CHECKS = 20


@dataclass
class SyncCheckResult:
    """Result of a sync check for one tenant."""

    tenant_id: int
    missing_calls: list[dict] = field(default_factory=list)
    missing_sms: list[dict] = field(default_factory=list)
    stale_deliveries: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_discrepancies(self) -> int:
        return len(self.missing_calls) + len(self.missing_sms) + len(self.stale_deliveries)


class TelnyxSyncMonitorService:
    """Reconciles local DB data against the Telnyx API."""

    async def run_sync_check(
        self, db: AsyncSession, tenant_id: int, lookback_hours: int = 2
    ) -> SyncCheckResult:
        """Run a full sync check for a single tenant.

        Args:
            db: Database session
            tenant_id: Tenant to check
            lookback_hours: How far back to look (default 2 hours)

        Returns:
            SyncCheckResult with any discrepancies found
        """
        result = SyncCheckResult(tenant_id=tenant_id)
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

        # Get tenant configs
        sms_config = await self._get_sms_config(db, tenant_id)
        voice_config = await self._get_voice_config(db, tenant_id)

        if not sms_config or not sms_config.telnyx_api_key:
            result.errors.append("No Telnyx API key configured")
            return result

        if not voice_config or not voice_config.telnyx_agent_id:
            result.errors.append("No Telnyx agent configured")
            return result

        # Fetch recent conversations from Telnyx
        ai_service = TelnyxAIService(api_key=sms_config.telnyx_api_key)
        telnyx_conversations = await ai_service.list_recent_conversations()

        if not telnyx_conversations:
            logger.info(f"[TELNYX-SYNC] Tenant {tenant_id}: No recent Telnyx conversations")
            return result

        logger.info(
            f"[TELNYX-SYNC] Tenant {tenant_id}: Checking {len(telnyx_conversations)} "
            f"Telnyx conversations against local DB (lookback={lookback_hours}h)"
        )

        # Run checks
        result.missing_calls = await self._check_missing_calls(
            db, tenant_id, telnyx_conversations, cutoff
        )
        result.missing_sms = await self._check_missing_sms(
            db, tenant_id, telnyx_conversations, cutoff
        )
        result.stale_deliveries = await self._check_stale_deliveries(
            db, tenant_id, cutoff, ai_service
        )

        # Persist discrepancies
        await self._store_results(db, result)

        logger.info(
            f"[TELNYX-SYNC] Tenant {tenant_id}: Found {result.total_discrepancies} discrepancies "
            f"(calls={len(result.missing_calls)}, sms={len(result.missing_sms)}, "
            f"delivery={len(result.stale_deliveries)})"
        )

        return result

    async def run_all_tenants(
        self, db: AsyncSession, lookback_hours: int = 2
    ) -> list[SyncCheckResult]:
        """Run sync check for all Telnyx-enabled tenants."""
        # Find tenants with telnyx_agent_id configured
        stmt = (
            select(TenantVoiceConfig.tenant_id)
            .where(TenantVoiceConfig.telnyx_agent_id.isnot(None))
        )
        rows = await db.execute(stmt)
        tenant_ids = [r[0] for r in rows.all()]

        logger.info(f"[TELNYX-SYNC] Running sync check for {len(tenant_ids)} tenants")

        results = []
        for tenant_id in tenant_ids:
            try:
                result = await self.run_sync_check(db, tenant_id, lookback_hours)
                results.append(result)
            except Exception as e:
                logger.error(f"[TELNYX-SYNC] Tenant {tenant_id} sync failed: {e}", exc_info=True)
                err_result = SyncCheckResult(tenant_id=tenant_id)
                err_result.errors.append(str(e))
                results.append(err_result)

        return results

    # ── Internal checks ──────────────────────────────────────────────

    async def _check_missing_calls(
        self,
        db: AsyncSession,
        tenant_id: int,
        telnyx_conversations: list[dict],
        cutoff: datetime,
    ) -> list[dict]:
        """Check for voice calls in Telnyx that are missing from our Call table."""
        missing = []

        # Filter to voice-like conversations
        voice_convs = []
        for conv in telnyx_conversations:
            metadata = conv.get("metadata", {}) or {}
            channel = (
                metadata.get("telnyx_conversation_channel")
                or conv.get("channel")
                or ""
            )
            call_control_id = (
                metadata.get("call_control_id")
                or metadata.get("telnyx_call_control_id")
                or conv.get("call_control_id")
            )
            # A conversation is voice if it has a call_control_id or channel is phone_call
            if call_control_id or channel in ("phone_call", "voice"):
                voice_convs.append((conv, call_control_id))

        if not voice_convs:
            return missing

        # Batch check which call_control_ids exist in our DB
        known_ids = set()
        all_ids = [cid for _, cid in voice_convs if cid]
        if all_ids:
            stmt = (
                select(Call.call_sid)
                .where(
                    and_(
                        Call.tenant_id == tenant_id,
                        Call.call_sid.in_(all_ids),
                    )
                )
            )
            rows = await db.execute(stmt)
            known_ids = {r[0] for r in rows.all()}

        for conv, call_control_id in voice_convs:
            if not call_control_id:
                continue

            # Skip if we already have this call
            if call_control_id in known_ids:
                continue

            # Check if conversation is within our lookback window
            created_at_str = conv.get("created_at") or conv.get("inserted_at", "")
            if created_at_str:
                try:
                    conv_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if conv_time < cutoff:
                        continue  # Too old for this check window
                except (ValueError, TypeError):
                    pass

            metadata = conv.get("metadata", {}) or {}
            missing.append({
                "telnyx_conversation_id": conv.get("id"),
                "telnyx_call_control_id": call_control_id,
                "channel": "voice",
                "phone": metadata.get("from") or metadata.get("to"),
                "telnyx_created_at": created_at_str,
            })

        return missing

    async def _check_missing_sms(
        self,
        db: AsyncSession,
        tenant_id: int,
        telnyx_conversations: list[dict],
        cutoff: datetime,
    ) -> list[dict]:
        """Check for SMS conversations in Telnyx that have no messages in our DB."""
        missing = []

        # Filter to SMS-like conversations
        sms_convs = []
        for conv in telnyx_conversations:
            metadata = conv.get("metadata", {}) or {}
            channel = (
                metadata.get("telnyx_conversation_channel")
                or conv.get("channel")
                or ""
            )
            call_control_id = (
                metadata.get("call_control_id")
                or conv.get("call_control_id")
            )
            # SMS = no call_control_id and channel is sms/messaging/empty
            if not call_control_id and channel not in ("phone_call", "voice"):
                sms_convs.append(conv)

        if not sms_convs:
            return missing

        for conv in sms_convs:
            conv_id = conv.get("id")
            if not conv_id:
                continue

            created_at_str = conv.get("created_at") or conv.get("inserted_at", "")
            if created_at_str:
                try:
                    conv_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if conv_time < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            # Check if we have messages with source=telnyx_ai_assistant for this conversation
            stmt = (
                select(func.count())
                .select_from(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    and_(
                        Conversation.tenant_id == tenant_id,
                        Conversation.channel == "sms",
                        Message.message_metadata["source"].as_string() == "telnyx_ai_assistant",
                    )
                )
            )
            result = await db.execute(stmt)
            count = result.scalar() or 0

            # If no AI assistant messages at all, we might be missing this conversation.
            # But we need a way to match Telnyx conv to our DB. Use phone number from metadata.
            metadata = conv.get("metadata", {}) or {}
            phone = metadata.get("from") or metadata.get("end_user_target") or metadata.get("to")

            if phone and count == 0:
                # More specific check: do we have ANY sms conversation with this phone recently?
                phone_check = (
                    select(func.count())
                    .select_from(Conversation)
                    .where(
                        and_(
                            Conversation.tenant_id == tenant_id,
                            Conversation.channel == "sms",
                            Conversation.phone_number == phone,
                            Conversation.created_at >= cutoff,
                        )
                    )
                )
                phone_result = await db.execute(phone_check)
                if (phone_result.scalar() or 0) == 0:
                    missing.append({
                        "telnyx_conversation_id": conv_id,
                        "channel": "sms",
                        "phone": phone,
                        "telnyx_created_at": created_at_str,
                    })

        return missing

    async def _check_stale_deliveries(
        self,
        db: AsyncSession,
        tenant_id: int,
        cutoff: datetime,
        ai_service: TelnyxAIService,
    ) -> list[dict]:
        """Check for outbound SMS with stale delivery statuses."""
        stale = []

        # Find recent outbound SMS messages with non-terminal delivery status
        stmt = (
            select(Message.id, Message.message_metadata, Conversation.id.label("conv_id"))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.channel == "sms",
                    Message.role == "assistant",
                    Message.created_at >= cutoff,
                    Message.message_metadata.isnot(None),
                )
            )
            .order_by(Message.created_at.desc())
            .limit(MAX_DELIVERY_CHECKS * 2)  # Fetch extra to filter in Python
        )
        rows = await db.execute(stmt)
        messages = rows.all()

        checked = 0
        for msg_id, metadata, conv_id in messages:
            if checked >= MAX_DELIVERY_CHECKS:
                break

            if not metadata:
                continue

            telnyx_msg_id = metadata.get("telnyx_message_id")
            current_status = metadata.get("delivery_status", "")

            if not telnyx_msg_id:
                continue

            # Only check non-terminal statuses
            if current_status in ("delivered", "failed", "delivery_failed", "sending_failed"):
                continue

            # Query Telnyx for actual status
            checked += 1
            telnyx_data = await ai_service.get_message_status(telnyx_msg_id)
            if not telnyx_data:
                continue

            actual_status = telnyx_data.get("to", [{}])
            # Telnyx message response structure varies; try common paths
            if isinstance(telnyx_data, dict):
                actual_status = (
                    telnyx_data.get("status")
                    or telnyx_data.get("delivery", {}).get("state")
                    or ""
                )

            if actual_status and actual_status != current_status:
                stale.append({
                    "message_id": msg_id,
                    "conversation_id": conv_id,
                    "telnyx_message_id": telnyx_msg_id,
                    "expected_status": current_status,
                    "actual_status": actual_status,
                })

                # Auto-fix: update our record with the real status
                update_msg = await db.get(Message, msg_id)
                if update_msg and update_msg.message_metadata:
                    new_metadata = dict(update_msg.message_metadata)
                    new_metadata["delivery_status"] = actual_status
                    new_metadata["sync_corrected_at"] = datetime.utcnow().isoformat()
                    update_msg.message_metadata = new_metadata

        return stale

    # ── Helpers ───────────────────────────────────────────────────────

    async def _get_sms_config(self, db: AsyncSession, tenant_id: int) -> TenantSmsConfig | None:
        stmt = select(TenantSmsConfig).where(TenantSmsConfig.tenant_id == tenant_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_voice_config(self, db: AsyncSession, tenant_id: int) -> TenantVoiceConfig | None:
        stmt = select(TenantVoiceConfig).where(TenantVoiceConfig.tenant_id == tenant_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _store_results(self, db: AsyncSession, result: SyncCheckResult) -> None:
        """Persist discrepancies to the telnyx_sync_results table."""
        records = []

        for item in result.missing_calls:
            records.append(TelnyxSyncResult(
                tenant_id=result.tenant_id,
                sync_type="missing_call",
                severity="warning",
                telnyx_conversation_id=item.get("telnyx_conversation_id"),
                telnyx_call_control_id=item.get("telnyx_call_control_id"),
                details=item,
            ))

        for item in result.missing_sms:
            records.append(TelnyxSyncResult(
                tenant_id=result.tenant_id,
                sync_type="missing_sms",
                severity="warning",
                telnyx_conversation_id=item.get("telnyx_conversation_id"),
                details=item,
            ))

        for item in result.stale_deliveries:
            records.append(TelnyxSyncResult(
                tenant_id=result.tenant_id,
                sync_type="stale_delivery",
                severity="info",
                telnyx_message_id=item.get("telnyx_message_id"),
                details=item,
                # Auto-fixed, so mark as backfilled
                status="backfilled",
                resolved_at=datetime.utcnow(),
                resolved_by="auto_backfill",
            ))

        if records:
            db.add_all(records)
            await db.flush()
