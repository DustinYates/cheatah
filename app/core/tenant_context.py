"""Tenant context manager for ensuring tenant isolation."""

from contextvars import ContextVar
from typing import Optional

# Context variable for tenant_id
tenant_id_var: ContextVar[Optional[int]] = ContextVar("tenant_id", default=None)


def set_tenant_context(tenant_id: int | None) -> None:
    """Set the current tenant context.

    Args:
        tenant_id: Tenant ID to set in context
    """
    tenant_id_var.set(tenant_id)


def get_tenant_context() -> int | None:
    """Get the current tenant context.

    Returns:
        Current tenant ID or None
    """
    return tenant_id_var.get()


def clear_tenant_context() -> None:
    """Clear the current tenant context."""
    tenant_id_var.set(None)

