"""API routes."""

from fastapi import APIRouter

from app.api.routes import admin, chat, conversations, prompts, tenant_setup, tenants, users

api_router = APIRouter()

# Public routes (no auth required)
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

# Protected routes (auth required)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(tenant_setup.router, prefix="/tenant-setup", tags=["tenant-setup"])

