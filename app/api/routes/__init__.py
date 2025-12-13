"""API routes."""

from fastapi import APIRouter

from app.api.routes import admin, admin_sms, auth, chat, conversations, profile, prompts, sms_webhooks, tenant_setup, tenants, users

api_router = APIRouter()

# Public routes (no auth required)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(sms_webhooks.router, prefix="/sms", tags=["sms"])

# Protected routes (auth required)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(profile.router, prefix="/tenant", tags=["profile"])
api_router.include_router(tenant_setup.router, prefix="/tenant-setup", tags=["tenant-setup"])
api_router.include_router(admin_sms.router, prefix="/admin/sms", tags=["admin-sms"])

