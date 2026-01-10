"""Tenant routes for tenant operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_current_user
from app.api.schemas.tenant import EmbedCodeResponse, TenantResponse, TenantUpdate
from app.persistence.database import get_db
from app.persistence.models.tenant import Tenant, User
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.repositories.prompt_repository import PromptRepository
from app.persistence.repositories.tenant_repository import TenantRepository
from app.settings import settings

router = APIRouter()

# Default API base URL for embed code if not configured
DEFAULT_API_BASE_URL = "https://chattercheatah-900139201687.us-central1.run.app"


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant_info(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Get current tenant information."""
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant associated with user",
        )

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
    )


@router.put("/me", response_model=TenantResponse)
async def update_current_tenant(
    tenant_update: TenantUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantResponse:
    """Update current tenant."""
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant associated with user",
        )

    tenant_repo = TenantRepository(db)
    update_data = {}
    if tenant_update.name is not None:
        update_data["name"] = tenant_update.name
    if tenant_update.is_active is not None:
        update_data["is_active"] = tenant_update.is_active

    tenant = await tenant_repo.update(None, tenant_id, **update_data)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        subdomain=tenant.subdomain,
        is_active=tenant.is_active,
        created_at=tenant.created_at.isoformat(),
    )


def _generate_embed_code(api_base_url: str, tenant_id: int) -> str:
    """Generate WordPress embed code HTML for a tenant."""
    return f"""<!-- 
Chatter Cheetah Chat Widget - WordPress Embed Code
Add this to your WordPress footer or use a plugin like "Insert Headers and Footers"
-->

<!-- Load the chat widget script -->
<script src="{api_base_url}/static/chat-widget.js"></script>

<!-- Initialize the widget after page loads -->
<script>
(function() {{
  // Wait for both the page and the widget script to load
  function initChatWidget() {{
    if (typeof ChatterCheetah !== 'undefined') {{
      try {{
        ChatterCheetah.init({{
          apiUrl: '{api_base_url}/api/v1',
          tenantId: {tenant_id},
          scrollBehavior: 'top'
        }});
        console.log('Chatter Cheetah widget initialized successfully');
      }} catch (error) {{
        console.error('Error initializing chat widget:', error);
      }}
    }} else {{
      // Retry if script hasn't loaded yet
      setTimeout(initChatWidget, 100);
    }}
  }}
  
  // Initialize when DOM is ready
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initChatWidget);
  }} else {{
    // DOM already loaded
    initChatWidget();
  }}
}})();
</script>"""


@router.get("/me/embed-code", response_model=EmbedCodeResponse)
async def get_tenant_embed_code(
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[int | None, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmbedCodeResponse:
    """Get tenant-specific WordPress embed code.
    
    Returns the HTML embed code that can be pasted into a WordPress site
    to add the chat widget. Also indicates whether the tenant has a
    published prompt bundle (required for the widget to work).
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant associated with user",
        )

    # Verify tenant exists
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(None, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Check if tenant has a published prompt bundle (v1) or active tenant config (v2)
    prompt_repo = PromptRepository(db)
    production_bundle = await prompt_repo.get_production_bundle(tenant_id)
    has_v1_prompt = production_bundle is not None

    # Check for v2 Tenant Config
    v2_config_result = await db.execute(
        select(TenantPromptConfig).where(
            TenantPromptConfig.tenant_id == tenant_id,
            TenantPromptConfig.is_active == True
        )
    )
    has_v2_config = v2_config_result.scalar_one_or_none() is not None

    has_published_prompt = has_v1_prompt or has_v2_config

    # Get API base URL from settings or use default
    api_base_url = settings.api_base_url or DEFAULT_API_BASE_URL

    # Generate embed code
    embed_code = _generate_embed_code(api_base_url, tenant_id)

    # Prepare warning if no published prompt or active config
    warning = None
    if not has_published_prompt:
        warning = (
            "Your chatbot is not live yet. Please configure and activate a prompt in the Prompts page "
            "before adding this code to your website. The widget will not respond to "
            "visitors until a prompt configuration is active."
        )

    return EmbedCodeResponse(
        embed_code=embed_code,
        tenant_id=tenant_id,
        api_url=api_base_url,
        has_published_prompt=has_published_prompt,
        warning=warning,
    )
