"""Process Jackrabbit enrollment events from Zapier."""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone_e164
from app.infrastructure.notifications import NotificationService
from app.persistence.models.lead import Lead
from app.persistence.models.notification import NotificationPriority, NotificationType

logger = logging.getLogger(__name__)


class EnrollmentService:
    """Match Jackrabbit enrollments to existing leads and tag as registered."""

    REGISTERED_TAG = "enrolled"
    REGISTERED_PIPELINE_STAGE = "registered"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_enrollment(
        self,
        tenant_id: int,
        jackrabbit_enroll_id: str | None,
        jackrabbit_family_id: str | None,
        phone: str | None,
        email: str | None,
        student_name: str | None,
        class_name: str | None,
        enrollment_date: str | None,
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Match an enrollment to a lead and tag it as registered.

        Returns:
            dict with `matched` (bool), `lead_id` (int|None), `already_processed` (bool).
        """
        normalized_phone = normalize_phone_e164(phone) if phone else None

        lead = await self._find_lead(tenant_id, normalized_phone, email)
        if not lead:
            logger.info(
                "Enrollment received but no matching lead",
                extra={
                    "tenant_id": tenant_id,
                    "phone": normalized_phone,
                    "email": email,
                    "jackrabbit_enroll_id": jackrabbit_enroll_id,
                },
            )
            return {"matched": False, "lead_id": None, "already_processed": False}

        enrollment_record = {
            "jackrabbit_enroll_id": jackrabbit_enroll_id,
            "jackrabbit_family_id": jackrabbit_family_id,
            "student_name": student_name,
            "class_name": class_name,
            "enrollment_date": enrollment_date,
            "recorded_at": datetime.utcnow().isoformat(),
        }

        # dict() copy so SQLAlchemy detects the change on JSON columns
        extra_data = dict(lead.extra_data or {})
        enrollments = list(extra_data.get("enrollments") or [])

        already_processed = False
        if jackrabbit_enroll_id:
            for existing in enrollments:
                if (
                    isinstance(existing, dict)
                    and existing.get("jackrabbit_enroll_id") == jackrabbit_enroll_id
                ):
                    already_processed = True
                    break

        if not already_processed:
            enrollments.append(enrollment_record)
            extra_data["enrollments"] = enrollments
            lead.extra_data = extra_data

        if lead.pipeline_stage != self.REGISTERED_PIPELINE_STAGE:
            lead.pipeline_stage = self.REGISTERED_PIPELINE_STAGE

        current_tags = list(lead.custom_tags or [])
        if not any(
            isinstance(t, str) and t.strip().lower() == self.REGISTERED_TAG
            for t in current_tags
        ):
            current_tags.append(self.REGISTERED_TAG)
            lead.custom_tags = current_tags

        await self.session.commit()
        await self.session.refresh(lead)

        if not already_processed:
            try:
                await self._notify(tenant_id, lead, student_name, class_name)
            except Exception as e:
                logger.warning(
                    f"Enrollment notification failed for lead {lead.id}: {e}",
                    exc_info=True,
                )

        return {
            "matched": True,
            "lead_id": lead.id,
            "already_processed": already_processed,
        }

    async def _find_lead(
        self, tenant_id: int, phone: str | None, email: str | None
    ) -> Lead | None:
        if not phone and not email:
            return None
        conditions = []
        if email:
            conditions.append(Lead.email == email)
        if phone:
            conditions.append(Lead.phone == phone)
        stmt = (
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .where(or_(*conditions))
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _notify(
        self,
        tenant_id: int,
        lead: Lead,
        student_name: str | None,
        class_name: str | None,
    ) -> None:
        display_name = lead.name or "A lead"
        student_part = (
            f" ({student_name})"
            if student_name and student_name != lead.name
            else ""
        )
        class_part = f" in {class_name}" if class_name else ""
        subject = f"New Enrollment: {display_name}{student_part}"
        message = (
            f"{display_name}{student_part} just enrolled{class_part}. "
            "Lead marked as registered."
        )

        notification_service = NotificationService(self.session)
        await notification_service.notify_admins(
            tenant_id=tenant_id,
            subject=subject,
            message=message,
            methods=["in_app"],
            metadata={
                "lead_id": lead.id,
                "student_name": student_name,
                "class_name": class_name,
            },
            notification_type=NotificationType.LEAD_CAPTURED,
            priority=NotificationPriority.NORMAL,
            action_url=f"/dashboard/leads/{lead.id}",
        )
