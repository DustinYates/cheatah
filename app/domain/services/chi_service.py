"""Customer Happiness Index (CHI) computation service.

Computes an explainable 0-100 score per conversation using behavioral,
timing, and outcome signals. No surveys required.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.escalation import Escalation
from app.persistence.models.sent_asset import SentAsset
from app.persistence.models.call import Call

logger = logging.getLogger(__name__)

# --- Signal weights (default) ---
WEIGHTS = {
    # Frustration signals (negative)
    "repeated_questions": -8,
    "rapid_bursts": -6,
    "all_caps": -4,
    "negative_sentiment": -10,
    "bot_loop": -15,
    "hangup_before_resolution": -12,
    "escalation_after_loop": -10,
    "long_duration_no_resolution": -8,
    # Satisfaction signals (positive)
    "positive_closing": 8,
    "no_rephrase_needed": 5,
    "first_attempt_resolution": 12,
    "user_completed_next_step": 10,
    # Outcome signals
    "resolved": 10,
    "escalated": -5,
    "repeat_contact_48h": -8,
}

# Profanity / strong negative keywords (case-insensitive)
_NEGATIVE_KEYWORDS = {
    "terrible", "awful", "horrible", "worst", "hate", "angry", "frustrated",
    "ridiculous", "useless", "stupid", "waste", "unacceptable", "disgusting",
    "pathetic", "incompetent", "scam", "fraud", "bullshit", "wtf", "damn",
    "hell", "crap", "suck", "sucks",
}

# Positive closing keywords
_POSITIVE_KEYWORDS = {
    "thank", "thanks", "great", "perfect", "awesome", "excellent",
    "appreciate", "helpful", "wonderful", "fantastic", "amazing",
}


@dataclass
class CHISignal:
    """A single detected signal contributing to the CHI score."""

    name: str
    weight: int
    detail: str = ""


@dataclass
class CHIResult:
    """Full CHI computation result."""

    score: float  # 0-100
    signals: list[CHISignal] = field(default_factory=list)
    frustration_score: float = 0.0
    satisfaction_score: float = 0.0
    outcome_score: float = 0.0

    def to_json(self) -> dict:
        """Serialize for storage in conversations.chi_signals."""
        return {
            "score": round(self.score, 1),
            "frustration_score": round(self.frustration_score, 1),
            "satisfaction_score": round(self.satisfaction_score, 1),
            "outcome_score": round(self.outcome_score, 1),
            "signals": [
                {"name": s.name, "weight": s.weight, "detail": s.detail}
                for s in self.signals
            ],
        }


def _similarity_simple(a: str, b: str) -> float:
    """Simple word-overlap similarity (Jaccard) for detecting rephrasing."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


class CHIService:
    """Computes Customer Happiness Index for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compute_for_conversation(
        self,
        conversation: Conversation,
        messages: list[Message] | None = None,
    ) -> CHIResult:
        """Compute CHI score for a single conversation.

        Args:
            conversation: The conversation to score
            messages: Pre-loaded messages (optional, will be loaded if None)

        Returns:
            CHIResult with score and signal breakdown
        """
        if messages is None:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.sequence_number)
            )
            result = await self.session.execute(stmt)
            messages = list(result.scalars().all())

        if not messages:
            return CHIResult(score=65.0)  # Neutral default for empty conversations

        user_messages = [m for m in messages if m.role == "user"]
        assistant_messages = [m for m in messages if m.role == "assistant"]
        signals: list[CHISignal] = []

        # --- Frustration signals ---
        self._detect_repeated_questions(user_messages, signals)
        self._detect_rapid_bursts(user_messages, signals)
        self._detect_all_caps(user_messages, signals)
        self._detect_negative_sentiment(user_messages, signals)
        self._detect_bot_loop(assistant_messages, signals)

        # Voice-specific: hangup before resolution
        if conversation.channel == "voice":
            await self._detect_hangup(conversation, signals)

        # Long duration without resolution
        self._detect_long_duration(conversation, messages, signals)

        # --- Satisfaction signals ---
        self._detect_positive_closing(user_messages, signals)
        self._detect_no_rephrase(user_messages, signals)
        self._detect_first_attempt_resolution(messages, signals)

        # User completed next step (sent_asset exists)
        await self._detect_next_step_completed(conversation, signals)

        # --- Outcome signals ---
        has_escalation = await self._detect_escalation(conversation, signals)
        has_loop_signal = any(s.name == "bot_loop" for s in signals)
        if has_escalation and has_loop_signal:
            signals.append(CHISignal(
                name="escalation_after_loop",
                weight=WEIGHTS["escalation_after_loop"],
                detail="Escalation triggered after bot loop detected",
            ))

        if not has_escalation:
            # Check for positive resolution indicators
            has_positive = any(s.name == "positive_closing" for s in signals)
            has_next_step = any(s.name == "user_completed_next_step" for s in signals)
            if has_positive or has_next_step:
                signals.append(CHISignal(
                    name="resolved",
                    weight=WEIGHTS["resolved"],
                    detail="Conversation resolved (positive close or action completed)",
                ))

        # Repeat contact within 48h
        await self._detect_repeat_contact(conversation, signals)

        # --- Compute final score ---
        frustration = sum(s.weight for s in signals if s.weight < 0 and s.name not in ("escalated", "repeat_contact_48h"))
        satisfaction = sum(s.weight for s in signals if s.weight > 0 and s.name not in ("resolved",))
        outcome = sum(s.weight for s in signals if s.name in ("resolved", "escalated", "repeat_contact_48h"))

        raw_score = 65.0 + frustration + satisfaction + outcome  # Base of 65
        score = max(0.0, min(100.0, raw_score))

        return CHIResult(
            score=score,
            signals=signals,
            frustration_score=frustration,
            satisfaction_score=satisfaction,
            outcome_score=outcome,
        )

    async def batch_compute(
        self,
        conversation_ids: list[int],
        batch_size: int = 50,
    ) -> dict[int, CHIResult]:
        """Batch compute CHI for multiple conversations.

        Args:
            conversation_ids: List of conversation IDs to process
            batch_size: Process in chunks to limit memory

        Returns:
            Dict mapping conversation_id to CHIResult
        """
        results: dict[int, CHIResult] = {}

        for i in range(0, len(conversation_ids), batch_size):
            batch_ids = conversation_ids[i : i + batch_size]

            # Load conversations with messages
            conv_stmt = (
                select(Conversation)
                .where(Conversation.id.in_(batch_ids))
            )
            conv_result = await self.session.execute(conv_stmt)
            conversations = list(conv_result.scalars().all())

            msg_stmt = (
                select(Message)
                .where(Message.conversation_id.in_(batch_ids))
                .order_by(Message.conversation_id, Message.sequence_number)
            )
            msg_result = await self.session.execute(msg_stmt)
            all_messages = list(msg_result.scalars().all())

            # Group messages by conversation
            messages_by_conv: dict[int, list[Message]] = {}
            for m in all_messages:
                messages_by_conv.setdefault(m.conversation_id, []).append(m)

            for conv in conversations:
                msgs = messages_by_conv.get(conv.id, [])
                chi = await self.compute_for_conversation(conv, msgs)
                results[conv.id] = chi

                # Persist result
                conv.chi_score = chi.score
                conv.chi_computed_at = datetime.utcnow()
                conv.chi_signals = chi.to_json()

            await self.session.commit()

        return results

    # --- Signal detection methods ---

    def _detect_repeated_questions(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect user rephrasing the same question."""
        if len(user_messages) < 2:
            return
        rephrase_count = 0
        for i in range(1, len(user_messages)):
            sim = _similarity_simple(
                user_messages[i - 1].content, user_messages[i].content
            )
            if sim > 0.6:
                rephrase_count += 1
        if rephrase_count > 0:
            signals.append(CHISignal(
                name="repeated_questions",
                weight=WEIGHTS["repeated_questions"],
                detail=f"{rephrase_count} rephrased message(s) detected",
            ))

    def _detect_rapid_bursts(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect 3+ user messages within 60 seconds."""
        if len(user_messages) < 3:
            return
        for i in range(len(user_messages) - 2):
            ts = [m.created_at for m in user_messages[i : i + 3]]
            if all(t is not None for t in ts):
                span = (ts[2] - ts[0]).total_seconds()
                if span <= 60:
                    signals.append(CHISignal(
                        name="rapid_bursts",
                        weight=WEIGHTS["rapid_bursts"],
                        detail=f"3 messages in {span:.0f}s",
                    ))
                    return  # One detection is enough

    def _detect_all_caps(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect messages that are predominantly ALL CAPS."""
        for m in user_messages:
            text = m.content.strip()
            if len(text) > 10:
                alpha_chars = [c for c in text if c.isalpha()]
                if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.5:
                    signals.append(CHISignal(
                        name="all_caps",
                        weight=WEIGHTS["all_caps"],
                        detail="ALL CAPS message detected",
                    ))
                    return

    def _detect_negative_sentiment(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect profanity or strongly negative language."""
        for m in user_messages:
            words = set(re.findall(r'\b\w+\b', m.content.lower()))
            matches = words & _NEGATIVE_KEYWORDS
            if matches:
                signals.append(CHISignal(
                    name="negative_sentiment",
                    weight=WEIGHTS["negative_sentiment"],
                    detail=f"Negative language detected",
                ))
                return

    def _detect_bot_loop(
        self, assistant_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect >3 similar bot responses (content loop)."""
        if len(assistant_messages) < 3:
            return
        # Check for high similarity between consecutive assistant messages
        similar_count = 0
        for i in range(1, len(assistant_messages)):
            sim = _similarity_simple(
                assistant_messages[i - 1].content, assistant_messages[i].content
            )
            if sim > 0.7:
                similar_count += 1
        if similar_count >= 2:  # 3+ similar messages
            signals.append(CHISignal(
                name="bot_loop",
                weight=WEIGHTS["bot_loop"],
                detail=f"{similar_count + 1} similar bot responses",
            ))

    async def _detect_hangup(
        self, conversation: Conversation, signals: list[CHISignal]
    ) -> None:
        """Detect short voice calls (hangup before resolution)."""
        try:
            stmt = (
                select(Call)
                .where(
                    Call.tenant_id == conversation.tenant_id,
                    Call.duration is not None,
                )
                .order_by(Call.started_at.desc())
                .limit(1)
            )
            # Match by phone number if available
            if conversation.phone_number:
                stmt = stmt.where(Call.from_number == conversation.phone_number)

            result = await self.session.execute(stmt)
            call = result.scalar_one_or_none()
            if call and call.duration and call.duration < 30:
                signals.append(CHISignal(
                    name="hangup_before_resolution",
                    weight=WEIGHTS["hangup_before_resolution"],
                    detail=f"Call ended after {call.duration}s",
                ))
        except Exception as e:
            logger.debug(f"Hangup detection skipped: {e}")

    def _detect_long_duration(
        self,
        conversation: Conversation,
        messages: list[Message],
        signals: list[CHISignal],
    ) -> None:
        """Detect conversations that run much longer than expected without resolution."""
        if len(messages) < 2:
            return
        first_ts = messages[0].created_at
        last_ts = messages[-1].created_at
        if first_ts and last_ts:
            duration_min = (last_ts - first_ts).total_seconds() / 60
            # Channel-specific thresholds
            threshold_map = {"sms": 30, "web": 15, "voice": 20}
            threshold = threshold_map.get(conversation.channel, 20)
            if duration_min > threshold and len(messages) > 8:
                signals.append(CHISignal(
                    name="long_duration_no_resolution",
                    weight=WEIGHTS["long_duration_no_resolution"],
                    detail=f"{duration_min:.0f} min conversation with {len(messages)} messages",
                ))

    def _detect_positive_closing(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect positive language in the last user message."""
        if not user_messages:
            return
        last_msg = user_messages[-1].content.lower()
        words = set(re.findall(r'\b\w+\b', last_msg))
        if words & _POSITIVE_KEYWORDS:
            signals.append(CHISignal(
                name="positive_closing",
                weight=WEIGHTS["positive_closing"],
                detail="Positive closing language detected",
            ))

    def _detect_no_rephrase(
        self, user_messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect that no rephrasing was needed (all messages dissimilar)."""
        if len(user_messages) < 2:
            return
        # Only add if repeated_questions was NOT detected
        has_rephrase = any(s.name == "repeated_questions" for s in signals)
        if not has_rephrase:
            signals.append(CHISignal(
                name="no_rephrase_needed",
                weight=WEIGHTS["no_rephrase_needed"],
                detail="No repeated questions detected",
            ))

    def _detect_first_attempt_resolution(
        self, messages: list[Message], signals: list[CHISignal]
    ) -> None:
        """Detect resolution within first few exchanges."""
        user_count = sum(1 for m in messages if m.role == "user")
        if user_count <= 2 and len(messages) <= 4:
            signals.append(CHISignal(
                name="first_attempt_resolution",
                weight=WEIGHTS["first_attempt_resolution"],
                detail=f"Resolved in {user_count} user message(s)",
            ))

    async def _detect_next_step_completed(
        self, conversation: Conversation, signals: list[CHISignal]
    ) -> None:
        """Detect if user completed next step (e.g. registration link was sent)."""
        try:
            stmt = (
                select(func.count())
                .select_from(SentAsset)
                .where(
                    SentAsset.tenant_id == conversation.tenant_id,
                    SentAsset.conversation_id == conversation.id,
                )
            )
            result = await self.session.execute(stmt)
            count = result.scalar() or 0
            if count > 0:
                signals.append(CHISignal(
                    name="user_completed_next_step",
                    weight=WEIGHTS["user_completed_next_step"],
                    detail=f"{count} asset(s) sent to user",
                ))
        except Exception as e:
            logger.debug(f"Next step detection skipped: {e}")

    async def _detect_escalation(
        self, conversation: Conversation, signals: list[CHISignal]
    ) -> bool:
        """Detect if conversation was escalated."""
        try:
            stmt = (
                select(func.count())
                .select_from(Escalation)
                .where(Escalation.conversation_id == conversation.id)
            )
            result = await self.session.execute(stmt)
            count = result.scalar() or 0
            if count > 0:
                signals.append(CHISignal(
                    name="escalated",
                    weight=WEIGHTS["escalated"],
                    detail=f"{count} escalation(s)",
                ))
                return True
        except Exception as e:
            logger.debug(f"Escalation detection skipped: {e}")
        return False

    async def _detect_repeat_contact(
        self, conversation: Conversation, signals: list[CHISignal]
    ) -> None:
        """Detect if this contact had another conversation within 48h."""
        if not conversation.phone_number and not conversation.contact_id:
            return
        try:
            window_start = conversation.created_at - timedelta(hours=48)
            window_end = conversation.created_at

            stmt = select(func.count()).select_from(Conversation).where(
                Conversation.tenant_id == conversation.tenant_id,
                Conversation.id != conversation.id,
                Conversation.created_at >= window_start,
                Conversation.created_at < window_end,
            )

            if conversation.phone_number:
                stmt = stmt.where(Conversation.phone_number == conversation.phone_number)
            elif conversation.contact_id:
                stmt = stmt.where(Conversation.contact_id == conversation.contact_id)

            result = await self.session.execute(stmt)
            count = result.scalar() or 0
            if count > 0:
                signals.append(CHISignal(
                    name="repeat_contact_48h",
                    weight=WEIGHTS["repeat_contact_48h"],
                    detail=f"{count} prior conversation(s) in 48h window",
                ))
        except Exception as e:
            logger.debug(f"Repeat contact detection skipped: {e}")
