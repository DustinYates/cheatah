"""Database models."""

from app.persistence.models.audit_log import AuditAction, AuditLog
from app.persistence.models.call import Call
from app.persistence.models.call_summary import CallSummary
from app.persistence.models.contact import Contact
from app.persistence.models.contact_alias import ContactAlias
from app.persistence.models.contact_merge_log import ContactMergeLog
from app.persistence.models.lead_merge_log import LeadMergeLog
from app.persistence.models.conversation import Conversation, Message
from app.persistence.models.escalation import Escalation
from app.persistence.models.lead import Lead
from app.persistence.models.notification import Notification, NotificationPriority, NotificationType
from app.persistence.models.prompt import PromptBundle, PromptSection
from app.persistence.models.sms_opt_in import SmsOptIn
from app.persistence.models.do_not_contact import DoNotContact
from app.persistence.models.tenant import Tenant, TenantBusinessProfile, User
from app.persistence.models.email_ingestion_log import EmailIngestionLog, IngestionStatus
from app.persistence.models.tenant_email_config import EmailConversation, TenantEmailConfig
from app.persistence.models.tenant_sms_config import TenantSmsConfig
from app.persistence.models.tenant_voice_config import TenantVoiceConfig
from app.persistence.models.tenant_widget_config import TenantWidgetConfig
from app.persistence.models.tenant_calendar_config import TenantCalendarConfig
from app.persistence.models.tenant_customer_service_config import TenantCustomerServiceConfig
from app.persistence.models.tenant_prompt_config import TenantPromptConfig
from app.persistence.models.widget_event import WidgetEvent
from app.persistence.models.zapier_request import ZapierRequest
from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.models.config_snapshot import ConfigSnapshot
from app.persistence.models.sent_asset import SentAsset
from app.persistence.models.voice_ab_test import VoiceABTest, VoiceABTestVariant
from app.persistence.models.sms_burst_incident import SmsBurstIncident
from app.persistence.models.sms_burst_config import SmsBurstConfig
from app.persistence.models.communications_health_snapshot import CommunicationsHealthSnapshot
from app.persistence.models.anomaly_alert import AnomalyAlert
from app.persistence.models.service_health_incident import ServiceHealthIncident
from app.persistence.models.drip_campaign import DripCampaign, DripCampaignStep, DripEnrollment
from app.persistence.models.customer import Customer
from app.persistence.models.tenant_customer_support_config import TenantCustomerSupportConfig
from app.persistence.models.tenant_pipeline_stage import TenantPipelineStage
from app.persistence.models.forum import (
    Forum,
    ForumCategory,
    ForumComment,
    ForumCommentVote,
    ForumPost,
    ForumVote,
    GroupRole,
    PostStatus,
    UserGroup,
    UserGroupMembership,
)

__all__ = [
    "AuditAction",
    "AuditLog",
    "Call",
    "CallSummary",
    "Tenant",
    "TenantBusinessProfile",
    "User",
    "Conversation",
    "Message",
    "Lead",
    "Contact",
    "ContactAlias",
    "ContactMergeLog",
    "LeadMergeLog",
    "EmailConversation",
    "EmailIngestionLog",
    "IngestionStatus",
    "PromptBundle",
    "PromptSection",
    "TenantEmailConfig",
    "TenantSmsConfig",
    "TenantVoiceConfig",
    "TenantWidgetConfig",
    "SmsOptIn",
    "DoNotContact",
    "Escalation",
    "Notification",
    "NotificationType",
    "NotificationPriority",
    "TenantCustomerServiceConfig",
    "TenantPromptConfig",
    "WidgetEvent",
    "ZapierRequest",
    "JackrabbitCustomer",
    "ConfigSnapshot",
    "SentAsset",
    "TenantCalendarConfig",
    "SmsBurstIncident",
    "SmsBurstConfig",
    "CommunicationsHealthSnapshot",
    "AnomalyAlert",
    "ServiceHealthIncident",
    "Customer",
    "TenantCustomerSupportConfig",
    # Forum models
    "Forum",
    "ForumCategory",
    "ForumComment",
    "ForumCommentVote",
    "ForumPost",
    "ForumVote",
    "GroupRole",
    "PostStatus",
    "UserGroup",
    "UserGroupMembership",
    # Voice A/B testing
    "VoiceABTest",
    "VoiceABTestVariant",
    # Pipeline stages
    "TenantPipelineStage",
]

