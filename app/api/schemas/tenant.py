"""Tenant-related schemas."""

from datetime import date

from pydantic import BaseModel


class TenantCreate(BaseModel):
    """Tenant creation request."""

    name: str
    subdomain: str
    is_active: bool = True


class TenantUpdate(BaseModel):
    """Tenant update request."""

    name: str | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    """Tenant response."""

    id: int
    name: str
    subdomain: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class AdminTenantUpdate(BaseModel):
    """Admin tenant update request."""

    tenant_number: str | None = None
    end_date: date | None = None
    tier: str | None = None
    name: str | None = None
    is_active: bool | None = None


class AdminTenantResponse(BaseModel):
    """Admin tenant response."""

    id: int
    tenant_number: str | None
    name: str
    subdomain: str
    is_active: bool
    created_at: str
    end_date: str | None
    tier: str | None

    class Config:
        from_attributes = True


class EmbedCodeResponse(BaseModel):
    """Response containing tenant-specific embed code for WordPress integration."""

    embed_code: str
    tenant_id: int
    api_url: str
    has_published_prompt: bool
    warning: str | None = None


class TenantServiceStatus(BaseModel):
    """Status of a single service for a tenant."""

    enabled: bool = False
    configured: bool = False


class TenantServicesOverview(BaseModel):
    """Overview of all services for a tenant."""

    sms: TenantServiceStatus = TenantServiceStatus()
    voice: TenantServiceStatus = TenantServiceStatus()
    email: TenantServiceStatus = TenantServiceStatus()
    widget: TenantServiceStatus = TenantServiceStatus()
    customer_service: TenantServiceStatus = TenantServiceStatus()
    prompt: TenantServiceStatus = TenantServiceStatus()


class TenantOverviewStats(BaseModel):
    """Stats for a single tenant in the overview."""

    id: int
    tenant_number: str | None = None
    name: str
    subdomain: str
    is_active: bool
    tier: str | None
    total_conversations: int = 0
    total_leads: int = 0
    total_contacts: int = 0
    last_activity: str | None = None
    # Gmail status
    gmail_connected: bool = False
    gmail_email: str | None = None
    gmail_watch_active: bool = False
    # Phone numbers
    telnyx_phone_numbers: list[str] = []
    # SMS stats
    sms_incoming_count: int = 0
    sms_outgoing_count: int = 0
    # Call stats
    call_count: int = 0
    call_minutes: float = 0.0
    # Lead sources
    chatbot_leads_count: int = 0
    # Services overview
    services: TenantServicesOverview | None = None
    # Alerts
    active_alerts_count: int = 0
    alert_severity: str | None = None  # "critical", "warning", "info"


class TenantConfigDetailResponse(BaseModel):
    """Detailed configuration for a tenant's services."""

    tenant_id: int
    tenant_name: str
    sms: dict | None = None
    voice: dict | None = None
    email: dict | None = None
    widget: dict | None = None
    customer_service: dict | None = None
    prompt: dict | None = None


class TenantsOverviewResponse(BaseModel):
    """Response for master admin tenant overview."""

    tenants: list[TenantOverviewStats]
    total_tenants: int
    active_tenants: int
