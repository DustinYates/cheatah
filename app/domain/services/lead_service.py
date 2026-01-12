"""Lead service for managing lead capture (schema + state only)."""

import logging
import re
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.models.lead import Lead
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.lead_repository import LeadRepository

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
    ) -> Lead:
        """Capture a lead (create lead record).

        Args:
            tenant_id: Tenant ID
            conversation_id: Optional conversation ID
            email: Optional email
            phone: Optional phone (will be normalized to E.164 format)
            name: Optional name
            metadata: Optional metadata dictionary (mapped to extra_data)

        Returns:
            Created lead
        """
        # Normalize phone to E.164 format for SMS compatibility
        normalized_phone = normalize_phone_e164(phone) if phone else None
        if phone and normalized_phone != phone:
            logger.info(f"Normalized phone from '{phone}' to '{normalized_phone}'")

        lead = await self.lead_repo.create(
            tenant_id,
            conversation_id=conversation_id,
            email=email,
            phone=normalized_phone,
            name=name,
            extra_data=metadata,  # Map metadata parameter to extra_data field
        )

        # Schedule SMS follow-up if conditions are met
        print(f"[FOLLOWUP_CHECK] lead_id={lead.id}, phone={normalized_phone}, metadata={metadata}", flush=True)
        logger.info(f"[FOLLOWUP_CHECK] lead_id={lead.id}, phone={normalized_phone}, metadata={metadata}")
        if normalized_phone and metadata and metadata.get("source") in ["voice_call", "sms", "email"]:
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

        return lead

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
            if lead.name and force_name_update:
                logger.info(f"Overwriting lead {lead_id} name from '{lead.name}' to '{name}' (explicit introduction)")
            lead.name = name
            updated = True
            logger.info(f"Updated lead {lead_id} with name: {name}")

        if updated:
            await self.session.commit()
            await self.session.refresh(lead)

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

        lead.created_at = occurred_at or datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def _create_contact_from_lead(self, tenant_id: int, lead: Lead) -> Contact | None:
        """Create a Contact from a verified lead if one doesn't already exist.

        Args:
            tenant_id: Tenant ID
            lead: Lead to create contact from

        Returns:
            Created Contact or None if contact already exists
        """
        logger.info(f"Creating contact from lead {lead.id}: email={lead.email}, phone={lead.phone}, name={lead.name}")
        
        try:
            # Check if a contact already exists with this email or phone
            existing_contact = await self.contact_repo.get_by_email_or_phone(
                tenant_id, email=lead.email, phone=lead.phone
            )
            
            if existing_contact:
                logger.info(f"Found existing contact {existing_contact.id} for lead {lead.id}")
                updated = False
                # If contact exists but doesn't have lead_id, link it
                if not existing_contact.lead_id:
                    existing_contact.lead_id = lead.id
                    updated = True
                # Update missing fields from lead
                if lead.phone and not existing_contact.phone:
                    existing_contact.phone = lead.phone
                    updated = True
                    logger.info(f"Updated contact {existing_contact.id} with phone from lead {lead.id}")
                if lead.email and not existing_contact.email:
                    existing_contact.email = lead.email
                    updated = True
                    logger.info(f"Updated contact {existing_contact.id} with email from lead {lead.id}")
                if lead.name and not existing_contact.name:
                    existing_contact.name = lead.name
                    updated = True
                    logger.info(f"Updated contact {existing_contact.id} with name from lead {lead.id}")
                # Don't commit here - let the caller commit
                return existing_contact
            
            # Create new contact from lead data
            logger.info(f"Creating new contact for lead {lead.id}")
            # Determine source from lead metadata
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
            # Don't commit here - let the caller commit to maintain transaction integrity
            # The caller (update_lead_status) will commit both the lead status change and contact creation
            logger.info(f"Added contact to session for lead {lead.id}")
            return contact
        except Exception as e:
            logger.error(f"Error creating contact from lead {lead.id}: {e}", exc_info=True)
            raise

    async def delete_lead(self, tenant_id: int, lead_id: int) -> bool:
        """Delete a lead by ID.
        
        Before deleting, nullifies any contact's lead_id and email_conversations.lead_id
        that references this lead to prevent foreign key constraint violations.
        
        Uses raw SQL to avoid ORM relationship loading which would query
        non-existent columns in the Contact model.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            True if deleted, False if not found
        """
        # First, check if lead exists using raw SQL to avoid relationship loading
        result = await self.session.execute(
            text("SELECT id FROM leads WHERE id = :lead_id AND tenant_id = :tenant_id"),
            {"lead_id": lead_id, "tenant_id": tenant_id}
        )
        if result.scalar_one_or_none() is None:
            return False
        
        # Nullify any contact's lead_id that references this lead using raw SQL
        await self.session.execute(
            text("UPDATE contacts SET lead_id = NULL WHERE tenant_id = :tenant_id AND lead_id = :lead_id"),
            {"tenant_id": tenant_id, "lead_id": lead_id}
        )
        
        # Nullify any email_conversation's lead_id that references this lead using raw SQL
        # This prevents the foreign key constraint violation on email_conversations_lead_id_fkey
        await self.session.execute(
            text("UPDATE email_conversations SET lead_id = NULL WHERE tenant_id = :tenant_id AND lead_id = :lead_id"),
            {"tenant_id": tenant_id, "lead_id": lead_id}
        )
        
        # Delete the lead using raw SQL to avoid relationship loading
        await self.session.execute(
            text("DELETE FROM leads WHERE id = :lead_id AND tenant_id = :tenant_id"),
            {"lead_id": lead_id, "tenant_id": tenant_id}
        )
        
        await self.session.commit()
        return True
