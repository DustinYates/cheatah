"""Lead service for managing lead capture (schema + state only)."""

import logging
import re
from datetime import datetime
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.models.lead import Lead
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.lead_repository import LeadRepository
from app.utils.name_validator import validate_name

logger = logging.getLogger(__name__)


def normalize_phone_e164(phone: str | None) -> str | None:
    """Normalize phone number to E.164 format (+1XXXXXXXXXX for US numbers).

    Handles various input formats:
    - 2817882316
    - (281)788-2316
    - 281-788-2316
    - 281.788.2316
    - +1 281 788 2316
    - 1-281-788-2316

    Args:
        phone: Raw phone number string

    Returns:
        Phone in E.164 format (+1XXXXXXXXXX) or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters except leading +
    digits = re.sub(r'\D', '', phone)

    # Handle US numbers
    if len(digits) == 10:
        # 10 digits: add +1 prefix
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # 11 digits starting with 1: add + prefix
        return f"+{digits}"
    elif len(digits) > 10 and phone.strip().startswith('+'):
        # International format: keep as-is with + prefix
        return f"+{digits}"

    # If already in E.164 format, return as-is
    if phone.startswith('+') and len(digits) >= 10:
        return f"+{digits}"

    logger.warning(f"Could not normalize phone number: {phone}")
    return phone  # Return original if we can't normalize (better than losing it)


def _lead_qualifies_for_auto_conversion(lead: Lead) -> bool:
    """Check if lead has sufficient info for automatic contact creation.

    A lead qualifies if it has:
    - A non-empty name
    - AND either a non-empty email OR phone

    Args:
        lead: Lead to check

    Returns:
        True if lead qualifies for auto-conversion
    """
    has_name = bool(lead.name and lead.name.strip())
    has_email = bool(lead.email and lead.email.strip())
    has_phone = bool(lead.phone and lead.phone.strip())
    return has_name and (has_email or has_phone)


class LeadService:
    """Service for lead management (schema + state only, no Twilio/Zapier logic)."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize lead service."""
        self.session = session
        self.lead_repo = LeadRepository(session)
        self.contact_repo = ContactRepository(session)

    async def capture_lead(
        self,
        tenant_id: int,
        conversation_id: int | None = None,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
        skip_dedup: bool = False,
        contact_id: int | None = None,
    ) -> Lead:
        """Capture a lead, deduplicating by email/phone when possible.

        If skip_dedup is False (default), searches for an existing lead with
        the same email or phone and updates it instead of creating a new one.

        Args:
            tenant_id: Tenant ID
            conversation_id: Optional conversation ID
            email: Optional email
            phone: Optional phone (will be normalized to E.164 format)
            name: Optional name
            metadata: Optional metadata dictionary (mapped to extra_data)
            skip_dedup: If True, always create a new lead even if one exists
                       with the same email/phone. Use for anonymous leads.
            contact_id: Optional contact ID to link the lead to an existing contact

        Returns:
            Created lead
        """
        # Normalize phone to E.164 format for SMS compatibility
        normalized_phone = normalize_phone_e164(phone) if phone else None
        if phone and normalized_phone != phone:
            logger.info(f"Normalized phone from '{phone}' to '{normalized_phone}'")

        # Validate name using strict validation
        validated_name = validate_name(name, require_explicit=True) if name else None
        if name and validated_name != name:
            logger.info(f"Name validation: '{name}' -> '{validated_name}'")

        # Auto-link to existing contact by phone/email if contact_id not provided
        if not contact_id and (normalized_phone or email):
            existing_contact = await self.contact_repo.get_by_email_or_phone(
                tenant_id, email=email, phone=normalized_phone
            )
            if existing_contact:
                contact_id = existing_contact.id
                logger.info(f"Auto-linked lead to existing contact {contact_id} by phone={normalized_phone} or email={email}")

        # Check for existing lead with same email or phone (unless skip_dedup is set)
        existing_lead = None
        if not skip_dedup:
            existing_lead = await self._find_existing_lead(tenant_id, email, normalized_phone)
        else:
            logger.info(f"Skipping deduplication for new chatbot lead (skip_dedup=True)")

        if existing_lead:
            logger.info(f"Found existing lead {existing_lead.id} for email={email}, phone={normalized_phone}")
            # Update existing lead with new info
            updated = False
            if validated_name and not existing_lead.name:
                existing_lead.name = validated_name
                updated = True
            if email and not existing_lead.email:
                existing_lead.email = email
                updated = True
            if normalized_phone and not existing_lead.phone:
                existing_lead.phone = normalized_phone
                updated = True
            if conversation_id and not existing_lead.conversation_id:
                existing_lead.conversation_id = conversation_id
                updated = True
            # Merge metadata
            if metadata:
                if existing_lead.extra_data:
                    # Preserve existing data, add new source info
                    merged = dict(existing_lead.extra_data)
                    if "sources" not in merged:
                        merged["sources"] = [merged.get("source", "unknown")]
                    if metadata.get("source") and metadata["source"] not in merged["sources"]:
                        merged["sources"].append(metadata["source"])
                    merged.update({k: v for k, v in metadata.items() if k != "source"})
                    existing_lead.extra_data = merged
                else:
                    existing_lead.extra_data = metadata
                updated = True
            # Update timestamp so lead appears at top
            existing_lead.updated_at = datetime.utcnow()
            if updated:
                await self.session.commit()
                await self.session.refresh(existing_lead)
            lead = existing_lead
        else:
            lead = await self.lead_repo.create(
                tenant_id,
                conversation_id=conversation_id,
                email=email,
                phone=normalized_phone,
                name=validated_name,  # Use validated name
                extra_data=metadata,  # Map metadata parameter to extra_data field
                contact_id=contact_id,  # Link to existing contact
            )

        # Schedule SMS follow-up if conditions are met
        print(f"[FOLLOWUP_CHECK] lead_id={lead.id}, phone={normalized_phone}, metadata={metadata}", flush=True)
        logger.info(f"[FOLLOWUP_CHECK] lead_id={lead.id}, phone={normalized_phone}, metadata={metadata}")
        if normalized_phone and metadata and metadata.get("source") in ["voice_call", "sms", "email", "chatbot"]:
            # Check if follow-up should be skipped (voice call not qualified/no promise)
            if metadata.get("skip_followup"):
                skip_reason = metadata.get("skip_followup_reason", "not qualified")
                print(f"[FOLLOWUP_CHECK] Skipping follow-up for lead {lead.id}: {skip_reason}", flush=True)
                logger.info(f"[FOLLOWUP_CHECK] Skipping follow-up for lead {lead.id}: {skip_reason}")
            else:
                print(f"[FOLLOWUP_CHECK] Conditions met, attempting to schedule follow-up for lead {lead.id}", flush=True)
                logger.info(f"[FOLLOWUP_CHECK] Conditions met, attempting to schedule follow-up for lead {lead.id}")
                try:
                    from app.domain.services.followup_service import FollowUpService
                    followup_service = FollowUpService(self.session)
                    task_name = await followup_service.schedule_followup(tenant_id, lead.id)
                    if task_name:
                        print(f"[FOLLOWUP_CHECK] Scheduled follow-up for lead {lead.id}: {task_name}", flush=True)
                        logger.info(f"Scheduled follow-up for lead {lead.id}: {task_name}")
                    else:
                        print(f"[FOLLOWUP_CHECK] schedule_followup returned None for lead {lead.id}", flush=True)
                        logger.info(f"[FOLLOWUP_CHECK] schedule_followup returned None for lead {lead.id}")
                except Exception as e:
                    # Don't fail lead creation if follow-up scheduling fails
                    print(f"[FOLLOWUP_CHECK] ERROR: Failed to schedule follow-up for lead {lead.id}: {e}", flush=True)
                    logger.error(f"Failed to schedule follow-up for lead {lead.id}: {e}", exc_info=True)
        else:
            print(f"[FOLLOWUP_CHECK] Conditions NOT met - phone={bool(normalized_phone)}, has_metadata={bool(metadata)}, source={metadata.get('source') if metadata else None}", flush=True)
            logger.info(f"[FOLLOWUP_CHECK] Conditions NOT met - phone={bool(normalized_phone)}, has_metadata={bool(metadata)}, source={metadata.get('source') if metadata else None}")

        # Check for auto-conversion to contact
        await self._check_and_auto_convert(tenant_id, lead)

        return lead

    async def _find_existing_lead(
        self, tenant_id: int, email: str | None, phone: str | None
    ) -> Lead | None:
        """Find existing lead by email or phone.

        Args:
            tenant_id: Tenant ID
            email: Email to search for
            phone: Phone to search for (should be normalized)

        Returns:
            Existing lead or None
        """
        if not email and not phone:
            return None

        from sqlalchemy import or_

        conditions = []
        if email:
            conditions.append(Lead.email == email)
        if phone:
            conditions.append(Lead.phone == phone)

        stmt = (
            select(Lead)
            .where(Lead.tenant_id == tenant_id, or_(*conditions))
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lead(self, tenant_id: int, lead_id: int) -> Lead | None:
        """Get a lead by ID.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            Lead or None if not found
        """
        return await self.lead_repo.get_by_id(tenant_id, lead_id)

    async def list_leads(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Lead]:
        """List leads for a tenant.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of leads
        """
        return await self.lead_repo.list(tenant_id, skip=skip, limit=limit)

    async def get_lead_by_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Lead | None:
        """Get lead by conversation ID.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Lead or None if not found
        """
        return await self.lead_repo.get_by_conversation(tenant_id, conversation_id)

    async def update_lead_info(
        self,
        tenant_id: int,
        lead_id: int,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
        force_name_update: bool = False,
    ) -> Lead | None:
        """Update lead information, only filling in missing fields.

        Updates email, phone, and/or name only if the current value is None/empty.
        Does not change lead status.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID to update
            email: Email to set if currently missing
            phone: Phone to set if currently missing
            name: Name to set if currently missing
            force_name_update: If True, overwrite existing name (used when user
                explicitly states their name like "my name is X" or "I'm X")

        Returns:
            Updated lead or None if not found
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            return None

        updated = False
        # Only update fields that are currently missing
        if email and not lead.email:
            lead.email = email
            updated = True
            logger.info(f"Updated lead {lead_id} with email: {email}")
        if phone and not lead.phone:
            normalized_phone = normalize_phone_e164(phone)
            lead.phone = normalized_phone
            updated = True
            logger.info(f"Updated lead {lead_id} with phone: {normalized_phone}")
        # For name: update if missing, OR if force_name_update is True (explicit name introduction)
        if name and (not lead.name or force_name_update):
            # Validate name before setting
            validated_name = validate_name(name, require_explicit=force_name_update)
            if validated_name:
                if lead.name and force_name_update:
                    logger.info(f"Overwriting lead {lead_id} name from '{lead.name}' to '{validated_name}' (explicit introduction)")
                lead.name = validated_name
                updated = True
                logger.info(f"Updated lead {lead_id} with name: {validated_name}")
            else:
                logger.info(f"Rejected invalid name for lead {lead_id}: '{name}'")

        if updated:
            await self.session.commit()
            await self.session.refresh(lead)

            # Check if updated fields now match another lead — merge if so
            lead = await self._check_and_merge_duplicate_leads(tenant_id, lead)

            # Check for auto-conversion after update (lead might now qualify)
            await self._check_and_auto_convert(tenant_id, lead)

        return lead

    async def update_lead_status(
        self, tenant_id: int, lead_id: int, status: str
    ) -> Lead | None:
        """Update lead status and create Contact if verified.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID
            status: New status ('new', 'verified', 'unknown')

        Returns:
            Updated lead or None if not found
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            return None
        
        old_status = lead.status
        lead.status = status
        
        # If verified (or re-verified), create a Contact record if one doesn't exist
        # This handles both new verifications and re-attempts for leads that were
        # verified before but failed to create contacts
        if status == 'verified':
            await self._create_contact_from_lead(tenant_id, lead)
        
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def bump_lead_activity(
        self,
        tenant_id: int,
        lead_id: int,
        occurred_at: datetime | None = None,
    ) -> Lead | None:
        """Update lead timestamp so recent activity sorts to the top."""
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            return None

        lead.updated_at = occurred_at or datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def _check_and_auto_convert(self, tenant_id: int, lead: Lead) -> Contact | None:
        """Check if lead qualifies for auto-conversion and create contact if so.

        Automatically converts qualifying leads to contacts without requiring
        manual verification. A lead qualifies if it has a name AND (email OR phone).

        Args:
            tenant_id: Tenant ID
            lead: Lead to check and potentially convert

        Returns:
            Created/linked Contact if auto-converted, None otherwise
        """
        if not _lead_qualifies_for_auto_conversion(lead):
            return None

        # Check if lead already has an associated contact (via lead.contact_id)
        if lead.contact_id:
            logger.debug(f"Lead {lead.id} already linked to contact {lead.contact_id}, skipping auto-conversion")
            return None

        # Also check legacy relationship (contact.lead_id)
        result = await self.session.execute(
            text("SELECT id FROM contacts WHERE lead_id = :lead_id LIMIT 1"),
            {"lead_id": lead.id}
        )
        if result.scalar_one_or_none() is not None:
            logger.debug(f"Lead {lead.id} already has a contact (legacy), skipping auto-conversion")
            return None

        logger.info(f"Auto-converting lead {lead.id} to contact: name={lead.name}, email={lead.email}, phone={lead.phone}")
        contact = await self._create_contact_from_lead(tenant_id, lead)
        await self.session.commit()
        return contact

    async def _create_contact_from_lead(self, tenant_id: int, lead: Lead) -> Contact | None:
        """Create a Contact from a verified lead, auto-merging if matches exist.

        Contacts are merged based on matching email OR phone. If multiple
        contacts match, they are automatically merged into one primary contact.

        Args:
            tenant_id: Tenant ID
            lead: Lead to create contact from

        Returns:
            Created or merged Contact, or None on error
        """
        logger.info(f"Creating contact from lead {lead.id}: email={lead.email}, phone={lead.phone}, name={lead.name}")

        try:
            # Find ALL contacts matching email OR phone for auto-merge
            matching_contacts = await self.contact_repo.get_all_by_email_or_phone(
                tenant_id, email=lead.email, phone=lead.phone
            )

            if len(matching_contacts) > 1:
                # Multiple contacts match - auto-merge them
                logger.info(f"Found {len(matching_contacts)} contacts matching lead {lead.id}, auto-merging")

                from app.domain.services.contact_merge_service import ContactMergeService
                merge_service = ContactMergeService(self.session)

                # Use oldest contact as primary (first in list since sorted by created_at)
                primary_contact = matching_contacts[0]
                secondary_ids = [c.id for c in matching_contacts[1:]]

                # Build field resolutions: prefer primary's values, but fill missing from others
                field_resolutions = {}
                for field in ['name', 'email', 'phone']:
                    primary_value = getattr(primary_contact, field)
                    if not primary_value:
                        # Find first secondary with this value
                        for secondary in matching_contacts[1:]:
                            secondary_value = getattr(secondary, field)
                            if secondary_value:
                                field_resolutions[field] = secondary.id
                                break
                        else:
                            field_resolutions[field] = "primary"
                    else:
                        field_resolutions[field] = "primary"

                # Use system user ID (0) for auto-merge
                primary_contact = await merge_service.merge_contacts(
                    tenant_id=tenant_id,
                    primary_contact_id=primary_contact.id,
                    secondary_contact_ids=secondary_ids,
                    field_resolutions=field_resolutions,
                    user_id=0  # System auto-merge
                )

                # Update primary with any missing data from lead
                await self._update_contact_from_lead(primary_contact, lead)
                # Link lead to primary contact via contact_id
                lead.contact_id = primary_contact.id
                logger.info(f"Auto-merged {len(secondary_ids)} contacts into contact {primary_contact.id}")
                return primary_contact

            elif len(matching_contacts) == 1:
                # Single match - update and link
                existing_contact = matching_contacts[0]
                logger.info(f"Found existing contact {existing_contact.id} for lead {lead.id}")
                await self._update_contact_from_lead(existing_contact, lead)
                # Link lead to contact via contact_id
                lead.contact_id = existing_contact.id
                return existing_contact

            # No matches - create new contact from lead data
            logger.info(f"Creating new contact for lead {lead.id}")
            source = 'web_chat_lead'
            if lead.extra_data and lead.extra_data.get('source') == 'voice_call':
                source = 'voice_call'
            contact = Contact(
                tenant_id=tenant_id,
                lead_id=lead.id,
                email=lead.email,
                phone=lead.phone,
                name=lead.name,
                source=source,
            )
            self.session.add(contact)
            await self.session.flush()  # Get contact ID
            # Link lead to new contact via contact_id
            lead.contact_id = contact.id
            logger.info(f"Created contact {contact.id} for lead {lead.id}")
            return contact
        except Exception as e:
            logger.error(f"Error creating contact from lead {lead.id}: {e}", exc_info=True)
            raise

    async def _update_contact_from_lead(self, contact: Contact, lead: Lead) -> None:
        """Update contact with data from lead, filling missing fields.

        Args:
            contact: Contact to update
            lead: Lead with data to use
        """
        updated = False
        # Link lead to contact if not already linked
        if not contact.lead_id:
            contact.lead_id = lead.id
            updated = True
        # Update missing fields from lead
        if lead.phone and not contact.phone:
            contact.phone = lead.phone
            updated = True
            logger.info(f"Updated contact {contact.id} with phone from lead {lead.id}")
        if lead.email and not contact.email:
            contact.email = lead.email
            updated = True
            logger.info(f"Updated contact {contact.id} with email from lead {lead.id}")
        if lead.name and not contact.name:
            contact.name = lead.name
            updated = True
            logger.info(f"Updated contact {contact.id} with name from lead {lead.id}")

    def _pick_primary_lead(self, lead_a: Lead, lead_b: Lead) -> tuple[Lead, Lead]:
        """Determine which lead should be primary (kept) vs secondary (merged in).

        Scores each lead by data richness. Primary = more data. Tie-break = older.

        Returns:
            (primary, secondary) tuple
        """
        def _score(lead: Lead) -> int:
            score = 0
            if lead.name and lead.name.strip():
                # Real names score higher than placeholders
                if lead.name.startswith("Caller ") or lead.name.startswith("SMS Contact "):
                    score += 0  # Placeholder name doesn't count
                else:
                    score += 2
            if lead.email:
                score += 1
            if lead.phone:
                score += 1
            if lead.conversation_id:
                score += 1
            if lead.contact_id:
                score += 1
            return score

        score_a = _score(lead_a)
        score_b = _score(lead_b)

        if score_a > score_b:
            return (lead_a, lead_b)
        elif score_b > score_a:
            return (lead_b, lead_a)
        else:
            # Tie-break: older lead is primary
            if lead_a.created_at <= lead_b.created_at:
                return (lead_a, lead_b)
            return (lead_b, lead_a)

    async def merge_leads(
        self,
        tenant_id: int,
        primary_lead_id: int,
        secondary_lead_id: int,
        user_id: int = 0,
    ) -> Lead:
        """Merge secondary lead into primary lead.

        Copies missing fields, reassigns child records, logs the merge,
        and deletes the secondary lead.

        Args:
            tenant_id: Tenant ID
            primary_lead_id: Lead to keep
            secondary_lead_id: Lead to merge in and delete
            user_id: Who initiated the merge (0 = system auto-merge)

        Returns:
            The updated primary lead
        """
        from app.persistence.models.call_summary import CallSummary
        from app.persistence.models.drip_campaign import DripEnrollment
        from app.persistence.models.email_ingestion_log import EmailIngestionLog
        from app.persistence.models.lead_merge_log import LeadMergeLog
        from app.persistence.models.tenant_email_config import EmailConversation

        primary = await self.lead_repo.get_by_id(tenant_id, primary_lead_id)
        secondary = await self.lead_repo.get_by_id(tenant_id, secondary_lead_id)

        if not primary or not secondary:
            raise ValueError(f"Lead not found: primary={primary_lead_id}, secondary={secondary_lead_id}")
        if primary.id == secondary.id:
            return primary

        logger.info(f"Merging lead {secondary.id} into lead {primary.id} for tenant {tenant_id}")

        # --- 1. Snapshot secondary before any changes ---
        secondary_snapshot = {
            "id": secondary.id,
            "name": secondary.name,
            "email": secondary.email,
            "phone": secondary.phone,
            "conversation_id": secondary.conversation_id,
            "contact_id": secondary.contact_id,
            "status": secondary.status,
            "extra_data": secondary.extra_data,
            "created_at": secondary.created_at.isoformat() if secondary.created_at else None,
        }

        # --- 2. Copy missing fields from secondary -> primary ---
        field_resolutions = {}

        # Name: prefer real names over placeholders
        if not primary.name or primary.name.startswith("Caller ") or primary.name.startswith("SMS Contact "):
            if secondary.name and not secondary.name.startswith("Caller ") and not secondary.name.startswith("SMS Contact "):
                primary.name = secondary.name
                field_resolutions["name"] = "secondary"
            else:
                field_resolutions["name"] = "primary"
        else:
            field_resolutions["name"] = "primary"

        if not primary.email and secondary.email:
            primary.email = secondary.email
            field_resolutions["email"] = "secondary"
        else:
            field_resolutions["email"] = "primary"

        if not primary.phone and secondary.phone:
            primary.phone = secondary.phone
            field_resolutions["phone"] = "secondary"
        else:
            field_resolutions["phone"] = "primary"

        if not primary.contact_id and secondary.contact_id:
            primary.contact_id = secondary.contact_id

        # --- 3. Deep-merge extra_data ---
        primary_extra = dict(primary.extra_data or {})
        secondary_extra = dict(secondary.extra_data or {})

        # Merge sources lists
        primary_sources = primary_extra.get("sources", [])
        if not primary_sources and primary_extra.get("source"):
            primary_sources = [primary_extra["source"]]
        secondary_sources = secondary_extra.get("sources", [])
        if not secondary_sources and secondary_extra.get("source"):
            secondary_sources = [secondary_extra["source"]]
        combined_sources = list(dict.fromkeys(primary_sources + secondary_sources))  # dedup, preserve order
        if combined_sources:
            primary_extra["sources"] = combined_sources

        # Merge voice_calls arrays
        primary_calls = primary_extra.get("voice_calls", [])
        secondary_calls = secondary_extra.get("voice_calls", [])
        if secondary_calls:
            primary_extra["voice_calls"] = primary_calls + secondary_calls

        # Track merged conversation IDs
        merged_convos = primary_extra.get("merged_conversation_ids", [])
        if secondary.conversation_id:
            merged_convos.append(secondary.conversation_id)
        if merged_convos:
            primary_extra["merged_conversation_ids"] = merged_convos

        primary.extra_data = primary_extra

        # --- 4. Reassign child FK records ---
        # call_summaries (nullable)
        await self.session.execute(
            update(CallSummary)
            .where(CallSummary.lead_id == secondary.id)
            .values(lead_id=primary.id)
        )

        # email_conversations (nullable)
        await self.session.execute(
            update(EmailConversation)
            .where(EmailConversation.lead_id == secondary.id)
            .values(lead_id=primary.id)
        )

        # email_ingestion_logs (nullable)
        await self.session.execute(
            update(EmailIngestionLog)
            .where(EmailIngestionLog.lead_id == secondary.id)
            .values(lead_id=primary.id)
        )

        # contacts.lead_id (legacy, nullable)
        await self.session.execute(
            update(Contact)
            .where(Contact.lead_id == secondary.id)
            .values(lead_id=primary.id)
        )

        # drip_enrollments (NOT NULL + unique constraint per tenant/campaign/lead)
        result = await self.session.execute(
            select(DripEnrollment).where(DripEnrollment.lead_id == secondary.id)
        )
        for enrollment in result.scalars().all():
            # Check if primary already enrolled in same campaign
            existing_result = await self.session.execute(
                select(DripEnrollment).where(
                    DripEnrollment.lead_id == primary.id,
                    DripEnrollment.campaign_id == enrollment.campaign_id,
                    DripEnrollment.tenant_id == tenant_id,
                )
            )
            if existing_result.scalar_one_or_none():
                # Primary already enrolled — delete secondary's enrollment
                await self.session.delete(enrollment)
            else:
                # Reassign to primary
                enrollment.lead_id = primary.id

        # --- 5. Create merge log ---
        merge_log = LeadMergeLog(
            tenant_id=tenant_id,
            primary_lead_id=primary.id,
            secondary_lead_id=secondary.id,
            merged_by=user_id,
            field_resolutions=field_resolutions,
            secondary_data_snapshot=secondary_snapshot,
        )
        self.session.add(merge_log)

        # --- 6. Delete secondary lead ---
        await self.session.execute(
            delete(Lead).where(Lead.id == secondary.id, Lead.tenant_id == tenant_id)
        )

        # --- 7. Update primary timestamp ---
        primary.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(primary)

        logger.info(
            f"Merged lead {secondary.id} into {primary.id}: "
            f"fields={field_resolutions}, "
            f"secondary_conversation_id={secondary_snapshot.get('conversation_id')}"
        )
        return primary

    async def _check_and_merge_duplicate_leads(
        self, tenant_id: int, lead: Lead
    ) -> Lead:
        """After updating a lead's email/phone, check if it now matches another lead.

        If duplicates are found, merge them keeping the one with more data as primary.

        Args:
            tenant_id: Tenant ID
            lead: The lead that was just updated

        Returns:
            The surviving lead (may be the original or a different primary)
        """
        from sqlalchemy import or_

        if not lead.email and not lead.phone:
            return lead

        conditions = []
        if lead.email:
            conditions.append(Lead.email == lead.email)
        if lead.phone:
            conditions.append(Lead.phone == lead.phone)

        stmt = (
            select(Lead)
            .where(
                Lead.tenant_id == tenant_id,
                Lead.id != lead.id,
                or_(*conditions),
            )
            .order_by(Lead.created_at.asc())
        )
        result = await self.session.execute(stmt)
        duplicates = list(result.scalars().all())

        if not duplicates:
            return lead

        logger.info(f"Found {len(duplicates)} duplicate leads for lead {lead.id}")

        for duplicate in duplicates:
            primary, secondary = self._pick_primary_lead(lead, duplicate)
            lead = await self.merge_leads(
                tenant_id=tenant_id,
                primary_lead_id=primary.id,
                secondary_lead_id=secondary.id,
            )

        return lead

    async def delete_lead(self, tenant_id: int, lead_id: int) -> bool:
        """Delete a lead by ID.

        Before deleting, nullifies any contact's lead_id and email_conversations.lead_id
        that references this lead to prevent foreign key constraint violations.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            True if deleted, False if not found
        """
        from app.persistence.models.call_summary import CallSummary
        from app.persistence.models.drip_campaign import DripEnrollment
        from app.persistence.models.email_ingestion_log import EmailIngestionLog
        from app.persistence.models.tenant_email_config import EmailConversation

        # Check if lead exists
        result = await self.session.execute(
            select(Lead.id).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
        )
        if result.scalar_one_or_none() is None:
            return False

        # Nullify any contact's lead_id that references this lead
        await self.session.execute(
            update(Contact)
            .where(Contact.tenant_id == tenant_id, Contact.lead_id == lead_id)
            .values(lead_id=None)
        )

        # Nullify any email_conversation's lead_id that references this lead
        await self.session.execute(
            update(EmailConversation)
            .where(EmailConversation.tenant_id == tenant_id, EmailConversation.lead_id == lead_id)
            .values(lead_id=None)
        )

        # Nullify call_summaries.lead_id
        await self.session.execute(
            update(CallSummary)
            .where(CallSummary.lead_id == lead_id)
            .values(lead_id=None)
        )

        # Nullify email_ingestion_logs.lead_id
        await self.session.execute(
            update(EmailIngestionLog)
            .where(EmailIngestionLog.lead_id == lead_id)
            .values(lead_id=None)
        )

        # Delete drip_enrollments (NOT NULL constraint — can't nullify)
        await self.session.execute(
            delete(DripEnrollment)
            .where(DripEnrollment.lead_id == lead_id)
        )

        # Delete the lead
        await self.session.execute(
            delete(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
        )

        await self.session.commit()
        return True
