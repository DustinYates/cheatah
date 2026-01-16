"""Validator to ensure qualification questions are answered before sending registration links."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.conversation import Message

logger = logging.getLogger(__name__)


@dataclass
class QualificationStatus:
    """Status of qualification requirements for registration link."""

    is_qualified: bool
    missing_requirements: list[str]
    collected_info: dict[str, Any]
    reason: str | None = None


class RegistrationQualificationValidator:
    """Validates that required qualification questions have been answered before sending registration links.

    According to the BSS level placement approach, before sending a registration link we need:
    1. Age group determination (infant/child/teen/adult)
    2. Experience/comfort level discussion
    3. Location preference (which location works best)
    """

    # Keywords indicating age group has been discussed
    AGE_KEYWORDS = {
        "infant": ["infant", "baby", "newborn", "months old", "under 3", "under three"],
        "child": ["child", "kid", "years old", "3-11", "toddler", "preschool", "elementary"],
        "teen": ["teen", "teenager", "12-17", "high school", "middle school"],
        "adult": ["adult", "18+", "grown up", "myself"],
    }

    # Keywords indicating experience level has been discussed
    EXPERIENCE_KEYWORDS = [
        "experience",
        "lessons before",
        "swim before",
        "comfortable",
        "water comfort",
        "float",
        "beginner",
        "advanced",
        "intermediate",
        "never swam",
        "first time",
        "scared of water",
        "loves water",
        "can swim",
        "can't swim",
        "cannot swim",
    ]

    # Keywords indicating location has been discussed
    LOCATION_KEYWORDS = [
        "location",
        "pool",
        "address",
        "near me",
        "closest",
        "which pool",
        "where",
        "branch",
        "site",
    ]

    # Keywords indicating a level recommendation was made
    # Include all BSS program levels
    LEVEL_KEYWORDS = [
        "recommend",
        "suggest",
        "level",
        "class",
        # BSS infant/toddler levels
        "tadpole",
        "swimboree",
        "seahorse",
        # BSS child levels
        "starfish",
        "minnow",
        "turtle 1",
        "turtle 2",
        "turtle",
        # BSS adult levels
        "adult level",
        "young adult",
        # BSS specialty
        "dolphin",
        "barracuda",
        "parent-child",
        "water babies",
        "adaptive",
        "private lesson",
    ]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize validator."""
        self.session = session

    async def check_qualification(
        self,
        tenant_id: int,
        conversation_id: int,
        messages: list[Message],
    ) -> QualificationStatus:
        """Check if the conversation has collected required qualification info.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            messages: Conversation message history

        Returns:
            QualificationStatus with qualification details
        """
        # Combine all messages into searchable text
        conversation_text = self._get_conversation_text(messages)

        # Check each requirement
        age_info = self._check_age_group(conversation_text)
        experience_info = self._check_experience(conversation_text)
        location_info = self._check_location(conversation_text)
        level_recommendation = self._check_level_recommendation(conversation_text)

        collected_info = {
            "age_group": age_info,
            "experience_discussed": experience_info.get("discussed", False),
            "location_discussed": location_info.get("discussed", False),
            "level_recommended": level_recommendation.get("recommended", False),
        }

        missing = []

        # Age group is required
        if not age_info:
            missing.append("age_group")

        # Level recommendation should be made before registration
        # This is the most important check - it means the bot has enough info
        # to suggest a specific class level
        if not level_recommendation.get("recommended"):
            missing.append("level_recommendation")

            # Experience level is only required if no level recommendation yet
            # Once a level is recommended, experience was implicitly considered
            if not experience_info.get("discussed"):
                missing.append("experience_level")

        # Location is recommended but not strictly required
        # (user might be exploring options)

        is_qualified = len(missing) == 0

        if not is_qualified:
            reason = f"Missing qualification info: {', '.join(missing)}. Need to determine student level before sending registration link."
        else:
            reason = None

        logger.info(
            f"Registration qualification check - tenant_id={tenant_id}, "
            f"conversation_id={conversation_id}, is_qualified={is_qualified}, "
            f"missing={missing}, collected={collected_info}"
        )

        return QualificationStatus(
            is_qualified=is_qualified,
            missing_requirements=missing,
            collected_info=collected_info,
            reason=reason,
        )

    def _get_conversation_text(self, messages: list[Message]) -> str:
        """Combine messages into searchable text.

        Args:
            messages: List of conversation messages

        Returns:
            Combined lowercase text
        """
        texts = []
        for msg in messages:
            content = msg.content if hasattr(msg, "content") else str(msg)
            if content:
                texts.append(content.lower())
        return " ".join(texts)

    def _check_age_group(self, text: str) -> str | None:
        """Check if age group has been determined.

        Args:
            text: Conversation text

        Returns:
            Age group if found, None otherwise
        """
        for age_group, keywords in self.AGE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return age_group

        # Check for explicit age mentions (e.g., "5 years old", "my 7 year old")
        age_pattern = r"\b(\d{1,2})\s*(?:year|yr)s?\s*old\b"
        match = re.search(age_pattern, text)
        if match:
            age = int(match.group(1))
            if age < 3:
                return "infant"
            elif age <= 11:
                return "child"
            elif age <= 17:
                return "teen"
            else:
                return "adult"

        # Check for month mentions for infants
        month_pattern = r"\b(\d{1,2})\s*(?:month)s?\s*old\b"
        if re.search(month_pattern, text):
            return "infant"

        return None

    def _check_experience(self, text: str) -> dict[str, Any]:
        """Check if experience/comfort level has been discussed.

        Args:
            text: Conversation text

        Returns:
            Dict with discussion status and details
        """
        discussed = False
        keywords_found = []

        for keyword in self.EXPERIENCE_KEYWORDS:
            if keyword in text:
                discussed = True
                keywords_found.append(keyword)

        return {
            "discussed": discussed,
            "keywords_found": keywords_found,
        }

    def _check_location(self, text: str) -> dict[str, Any]:
        """Check if location preference has been discussed.

        Args:
            text: Conversation text

        Returns:
            Dict with discussion status and details
        """
        discussed = False
        keywords_found = []

        for keyword in self.LOCATION_KEYWORDS:
            if keyword in text:
                discussed = True
                keywords_found.append(keyword)

        return {
            "discussed": discussed,
            "keywords_found": keywords_found,
        }

    def _check_level_recommendation(self, text: str) -> dict[str, Any]:
        """Check if a level recommendation has been made.

        Args:
            text: Conversation text

        Returns:
            Dict with recommendation status and details
        """
        recommended = False
        keywords_found = []

        for keyword in self.LEVEL_KEYWORDS:
            if keyword in text:
                recommended = True
                keywords_found.append(keyword)

        return {
            "recommended": recommended,
            "keywords_found": keywords_found,
        }
