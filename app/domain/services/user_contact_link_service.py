"""Service for linking users to contacts during signup."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.models.tenant import User
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserContactLinkService:
    """Service for auto-joining users to contacts based on email."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the user contact link service.

        Args:
            session: Database session
        """
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.user_repo = UserRepository(session)

    async def link_user_to_contact_by_email(
        self, user: User
    ) -> Contact | None:
        """Auto-link user to existing contact based on email match.

        Logic:
        1. Skip if user already has contact_id
        2. Find all contacts matching user's email in user's tenant
        3. Select oldest contact (MIN created_at)
        4. Update contact name if empty and user has name
        5. Link user.contact_id to selected contact

        Args:
            user: User object (must have email and tenant_id)

        Returns:
            Linked contact or None if no match found
        """
        # Skip if user already linked
        if user.contact_id:
            logger.info(f"User {user.id} already linked to contact {user.contact_id}")
            return None

        # Skip if user has no email or tenant
        if not user.email or not user.tenant_id:
            logger.warning(f"User {user.id} has no email or tenant_id")
            return None

        # Find all matching contacts
        matching_contacts = await self.contact_repo.get_all_by_email(
            tenant_id=user.tenant_id,
            email=user.email
        )

        if not matching_contacts:
            logger.info(f"No contacts found for user {user.id} email {user.email}")
            return None

        # Select oldest contact (already sorted by created_at asc)
        primary_contact = matching_contacts[0]
        logger.info(
            f"Found {len(matching_contacts)} contacts for {user.email}, "
            f"selected oldest: contact_id={primary_contact.id}"
        )

        # Update contact name if empty (extract from email local part)
        if not primary_contact.name:
            # Try to extract name from email local part
            name_from_email = user.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            await self.contact_repo.update_contact(
                tenant_id=user.tenant_id,
                contact_id=primary_contact.id,
                name=name_from_email
            )
            logger.info(f"Updated contact {primary_contact.id} name to {name_from_email}")

        # Link user to contact
        await self.user_repo.link_contact(user.id, primary_contact.id)
        logger.info(f"Linked user {user.id} to contact {primary_contact.id}")

        # Refresh to get updated contact
        await self.session.refresh(primary_contact)
        return primary_contact
