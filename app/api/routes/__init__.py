"""API routes."""

from fastapi import APIRouter

from app.api.routes import admin, admin_sms, admin_voice, auth, calls, chat, contacts, conversations, email_webhooks, leads, profile, prompts, prompt_interview, sms_webhooks, tenant_email, tenant_setup, tenants, users, tenant_sms, tenant_voice, voice_webhooks

api_router = APIRouter()

# Public routes (no auth required)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(sms_webhooks.router, prefix="/sms", tags=["sms-webhooks"])
api_router.include_router(voice_webhooks.router, prefix="/voice", tags=["voice-webhooks"])
api_router.include_router(email_webhooks.router, prefix="/email", tags=["email-webhooks"])

# Protected routes (auth required)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(prompt_interview.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(profile.router, prefix="/tenant", tags=["profile"])
api_router.include_router(tenant_setup.router, prefix="/tenant-setup", tags=["tenant-setup"])
api_router.include_router(admin_sms.router, prefix="/admin/sms", tags=["admin-sms"])
api_router.include_router(admin_voice.router, prefix="/admin/voice", tags=["admin-voice"])

# Tenant SMS settings (no Twilio creds exposed)
api_router.include_router(tenant_sms.router, prefix="/sms", tags=["sms"])

# Tenant Voice settings (no Twilio creds exposed)
api_router.include_router(tenant_voice.router, prefix="/voice", tags=["voice"])

# Tenant Email settings (Gmail OAuth)
api_router.include_router(tenant_email.router, prefix="/email", tags=["email"])

# Leads, Contacts, and Calls
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
