"""API routes."""

from fastapi import APIRouter

from app.api.routes import admin, admin_customer_service, admin_sms, admin_telephony, admin_voice, analytics, audit_logs, auth, calls, chat, contacts, conversations, customer_service_sms_webhooks, customer_service_voice_webhooks, email_webhooks, escalation_settings, leads, profile, prompts, prompt_config, prompt_interview, sendable_assets, sms_webhooks, telnyx_webhooks, tenant_email, tenant_setup, tenant_widget, tenants, users, tenant_sms, tenant_voice, voice_webhooks, zapier_webhooks

api_router = APIRouter()

# Public routes (no auth required)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(sms_webhooks.router, prefix="/sms", tags=["sms-webhooks"])
api_router.include_router(voice_webhooks.router, prefix="/voice", tags=["voice-webhooks"])
api_router.include_router(email_webhooks.router, prefix="/email", tags=["email-webhooks"])

# Customer service webhooks (public - Twilio/Zapier callbacks)
api_router.include_router(customer_service_sms_webhooks.router, prefix="/customer-service/sms", tags=["customer-service-sms"])
api_router.include_router(customer_service_voice_webhooks.router, prefix="/customer-service/voice", tags=["customer-service-voice"])
api_router.include_router(zapier_webhooks.router, prefix="/zapier", tags=["zapier"])
api_router.include_router(telnyx_webhooks.router, prefix="/telnyx", tags=["telnyx"])

# Protected routes (auth required)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(prompt_interview.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(prompt_config.router, prefix="/prompt-config", tags=["prompt-config"])
api_router.include_router(profile.router, prefix="/tenant", tags=["profile"])
api_router.include_router(tenant_setup.router, prefix="/tenant-setup", tags=["tenant-setup"])
api_router.include_router(admin_sms.router, prefix="/admin/sms", tags=["admin-sms"])
api_router.include_router(admin_voice.router, prefix="/admin/voice", tags=["admin-voice"])
api_router.include_router(admin_customer_service.router, prefix="/admin/customer-service", tags=["admin-customer-service"])
api_router.include_router(admin_telephony.router, prefix="/admin/telephony", tags=["admin-telephony"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# Tenant SMS settings (no Twilio creds exposed)
api_router.include_router(tenant_sms.router, prefix="/sms", tags=["sms"])

# Tenant Voice settings (no Twilio creds exposed)
api_router.include_router(tenant_voice.router, prefix="/voice", tags=["voice"])

# Tenant Email settings (Gmail OAuth)
api_router.include_router(tenant_email.router, prefix="/email", tags=["email"])

# Tenant Widget customization
api_router.include_router(tenant_widget.router, prefix="/widget", tags=["widget"])

# Leads, Contacts, and Calls
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])

# Sendable Assets (AI follow-up messaging configuration)
api_router.include_router(sendable_assets.router, prefix="/sendable-assets", tags=["sendable-assets"])

# Escalation Settings (human handoff alerts)
api_router.include_router(escalation_settings.router, prefix="/escalation", tags=["escalation"])

# Audit Logs (tenant admin and global admin access)
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit-logs"])
