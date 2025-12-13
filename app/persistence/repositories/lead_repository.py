"""Lead repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.lead import Lead
from app.persistence.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    """Repository for Lead entities."""

    def __init__(self, session: AsyncSession):
        """Initialize lead repository."""
        super().__init__(Lead, session)

