"""Contact merge service for merging contacts."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.persistence.models.contact import Contact
from app.persistence.models.contact_alias import ContactAlias
from app.persistence.models.lead import Lead
from app.persistence.models.conversation import Conversation
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.contact_alias_repository import ContactAliasRepository
from app.persistence.repositories.contact_merge_log_repository import ContactMergeLogRepository


class MergeConflict:
    """Represents a field conflict between contacts."""
    
    def __init__(self, field: str, values: dict[int, Any]):
        self.field = field
        self.values = values  # {contact_id: value}


class MergePreview:
    """Preview of a merge operation."""
    
    def __init__(
        self,
        contacts: list[Contact],
        conflicts: list[MergeConflict],
        suggested_primary_id: int | None = None
    ):
        self.contacts = contacts
        self.conflicts = conflicts
        self.suggested_primary_id = suggested_primary_id


class ContactMergeService:
    """Service for merging contacts."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize merge service."""
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.alias_repo = ContactAliasRepository(session)
        self.merge_log_repo = ContactMergeLogRepository(session)

    async def get_merge_preview(
        self, tenant_id: int, contact_ids: list[int]
    ) -> MergePreview:
        """Get a preview of merging contacts, showing conflicts.
        
        Args:
            tenant_id: Tenant ID
            contact_ids: List of contact IDs to preview merging
            
        Returns:
            MergePreview with contacts and conflicts
            
        Raises:
            ValueError: If fewer than 2 contacts or contacts not found
        """
        if len(contact_ids) < 2:
            raise ValueError("At least 2 contacts required for merge")
        
        contacts = await self.contact_repo.get_multiple_by_ids(tenant_id, contact_ids)
        
        if len(contacts) != len(contact_ids):
            found_ids = {c.id for c in contacts}
            missing = set(contact_ids) - found_ids
            raise ValueError(f"Contacts not found: {missing}")
        
        # Detect conflicts
        conflicts = []
        fields_to_check = ['name', 'email', 'phone']
        
        for field in fields_to_check:
            values = {}
            for contact in contacts:
                value = getattr(contact, field)
                if value:  # Only include non-null values
                    values[contact.id] = value
            
            # If we have more than one unique value, it's a conflict
            unique_values = set(values.values())
            if len(unique_values) > 1:
                conflicts.append(MergeConflict(field, values))
        
        # Suggest the oldest contact as primary (or the one with most data)
        suggested_primary = min(contacts, key=lambda c: c.created_at)
        
        return MergePreview(
            contacts=contacts,
            conflicts=conflicts,
            suggested_primary_id=suggested_primary.id
        )

    async def merge_contacts(
        self,
        tenant_id: int,
        primary_contact_id: int,
        secondary_contact_ids: list[int],
        field_resolutions: dict[str, int | str],
        user_id: int
    ) -> Contact:
        """Merge multiple contacts into one primary contact.
        
        Args:
            tenant_id: Tenant ID
            primary_contact_id: ID of the contact that will survive
            secondary_contact_ids: IDs of contacts to merge into primary
            field_resolutions: Dict mapping field names to either:
                - "primary" to use primary contact's value
                - contact_id (int) to use that contact's value
            user_id: ID of user performing the merge
            
        Returns:
            The merged primary contact
            
        Raises:
            ValueError: If contacts not found or invalid configuration
        """
        # Validate inputs
        if primary_contact_id in secondary_contact_ids:
            raise ValueError("Primary contact cannot be in secondary list")
        
        all_ids = [primary_contact_id] + secondary_contact_ids
        contacts = await self.contact_repo.get_multiple_by_ids(tenant_id, all_ids)
        
        if len(contacts) != len(all_ids):
            raise ValueError("One or more contacts not found")
        
        # Get primary and secondary contacts
        primary = next(c for c in contacts if c.id == primary_contact_id)
        secondaries = [c for c in contacts if c.id in secondary_contact_ids]
        
        # Resolve field conflicts and update primary contact
        update_data = {}
        # Handle case where field_resolutions might be None or empty
        if field_resolutions:
            for field, resolution in field_resolutions.items():
                if resolution == "primary":
                    continue  # Keep primary's value
                elif isinstance(resolution, int):
                    # Use value from specified contact
                    source_contact = next((c for c in contacts if c.id == resolution), None)
                    if source_contact:
                        value = getattr(source_contact, field)
                        if value:  # Only update if value exists
                            update_data[field] = value
        
        # Update primary contact with resolved values
        if update_data:
            for key, value in update_data.items():
                setattr(primary, key, value)
            await self.session.commit()
            # Re-fetch primary contact after commit to ensure it's still in session
            primary = await self.contact_repo.get_by_id_any_status(tenant_id, primary_contact_id)
            if not primary:
                raise ValueError(f"Primary contact {primary_contact_id} not found after update")
        
        # Create aliases from all contacts' values
        aliases_to_create = []
        fields_for_aliases = {
            'email': 'email',
            'phone': 'phone', 
            'name': 'name'
        }
        
        for field, alias_type in fields_for_aliases.items():
            # Collect all unique values for this field
            all_values = {}
            for contact in contacts:
                value = getattr(contact, field)
                if value and value not in all_values.values():
                    all_values[contact.id] = value
            
            # Determine which is primary value
            primary_value = getattr(primary, field)
            
            # Create aliases for all values
            for contact_id, value in all_values.items():
                # Skip if value is None or empty string
                if not value:
                    continue
                is_primary_alias = (value == primary_value)
                aliases_to_create.append({
                    'contact_id': primary_contact_id,
                    'alias_type': alias_type,
                    'value': str(value).strip(),  # Ensure it's a string and trimmed
                    'is_primary': is_primary_alias,
                    'source_contact_id': contact_id if contact_id != primary_contact_id else None
                })
        
        # Create aliases (skip if empty to avoid unnecessary database calls)
        if aliases_to_create:
            try:
                # Filter out any aliases that might already exist
                existing_aliases = await self.alias_repo.get_aliases_for_contact(primary_contact_id)
                existing_values = {(a.alias_type, a.value) for a in existing_aliases}
                aliases_to_create_filtered = [
                    a for a in aliases_to_create
                    if (a['alias_type'], a['value']) not in existing_values
                ]
                
                if aliases_to_create_filtered:
                    await self.alias_repo.create_aliases_bulk(aliases_to_create_filtered)
            except Exception as e:
                # Log but continue - alias creation failure shouldn't block merge
                import sys
                print(f"Warning: Failed to create some aliases: {e}", file=sys.stderr)
        
        # Update related entities to point to primary contact
        for secondary in secondaries:
            await self._reassign_related_entities(
                tenant_id, secondary.id, primary_contact_id
            )
            
            # Create merge log
            secondary_snapshot = {
                'name': secondary.name,
                'email': secondary.email,
                'phone': secondary.phone,
                'source': secondary.source,
                'created_at': secondary.created_at.isoformat() if secondary.created_at else None,
            }
            
            await self.merge_log_repo.create_merge_log(
                tenant_id=tenant_id,
                primary_contact_id=primary_contact_id,
                secondary_contact_id=secondary.id,
                merged_by=user_id,
                field_resolutions=field_resolutions,
                secondary_data_snapshot=secondary_snapshot
            )
            
            # Mark secondary as merged
            await self.contact_repo.mark_as_merged(
                tenant_id, secondary.id, primary_contact_id, user_id
            )
        
        # Re-fetch the primary contact to ensure we have the latest data
        primary = await self.contact_repo.get_by_id_any_status(tenant_id, primary_contact_id)
        if not primary:
            raise ValueError(f"Primary contact {primary_contact_id} not found after merge")
        
        return primary

    async def _reassign_related_entities(
        self,
        tenant_id: int,
        from_contact_id: int,
        to_contact_id: int
    ) -> None:
        """Reassign related entities from one contact to another.
        
        Args:
            tenant_id: Tenant ID
            from_contact_id: Contact ID to reassign from
            to_contact_id: Contact ID to reassign to
        """
        # Update leads that reference this contact
        leads_stmt = (
            update(Lead)
            .where(
                Lead.tenant_id == tenant_id,
                Lead.contact_id == from_contact_id
            )
            .values(contact_id=to_contact_id)
        )
        await self.session.execute(leads_stmt)
        
        # Update conversations that reference this contact
        convs_stmt = (
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.contact_id == from_contact_id
            )
            .values(contact_id=to_contact_id)
        )
        await self.session.execute(convs_stmt)

    async def get_combined_conversation_history(
        self, tenant_id: int, contact_id: int
    ) -> list[Conversation]:
        """Get combined conversation history including merged contacts.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Primary contact ID
            
        Returns:
            List of all conversations, including from merged contacts
        """
        from sqlalchemy.orm import selectinload
        
        # Get the primary contact and all contacts merged into it
        merged_contacts = await self.contact_repo.get_merged_contacts(tenant_id, contact_id)
        all_contact_ids = [contact_id] + [c.id for c in merged_contacts]
        
        # Get all conversations for these contacts
        # First via direct contact_id link
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.contact_id.in_(all_contact_ids)
            )
            .order_by(Conversation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        direct_conversations = list(result.scalars().all())
        
        # Also get conversations via lead_id chain
        # Get contacts with their lead IDs
        contacts = await self.contact_repo.get_multiple_by_ids(tenant_id, [contact_id])
        # Include merged contacts
        for mc in merged_contacts:
            mc_full = await self.contact_repo.get_by_id_any_status(tenant_id, mc.id)
            if mc_full:
                contacts.append(mc_full)
        
        lead_ids = [c.lead_id for c in contacts if c.lead_id]
        
        if lead_ids:
            # Get leads
            leads_stmt = select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.id.in_(lead_ids)
            )
            leads_result = await self.session.execute(leads_stmt)
            leads = leads_result.scalars().all()
            
            conv_ids = [l.conversation_id for l in leads if l.conversation_id]
            
            if conv_ids:
                # Get those conversations
                conv_stmt = (
                    select(Conversation)
                    .options(selectinload(Conversation.messages))
                    .where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.id.in_(conv_ids)
                    )
                )
                conv_result = await self.session.execute(conv_stmt)
                lead_conversations = list(conv_result.scalars().all())
                
                # Combine and dedupe
                all_conv_ids = {c.id for c in direct_conversations}
                for conv in lead_conversations:
                    if conv.id not in all_conv_ids:
                        direct_conversations.append(conv)
        
        # Sort by date
        direct_conversations.sort(key=lambda c: c.created_at, reverse=True)
        return direct_conversations

    async def get_merge_history(
        self, tenant_id: int, contact_id: int
    ) -> list[dict]:
        """Get merge history for a contact.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            
        Returns:
            List of merge history entries
        """
        logs = await self.merge_log_repo.get_merge_history_for_contact(
            tenant_id, contact_id
        )
        
        return [
            {
                'id': log.id,
                'merged_contact_id': log.secondary_contact_id,
                'merged_contact_data': log.secondary_data_snapshot,
                'merged_by': log.user.email if log.user else None,
                'merged_at': log.merged_at.isoformat() if log.merged_at else None,
                'field_resolutions': log.field_resolutions
            }
            for log in logs
        ]
