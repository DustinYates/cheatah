# Database Schema (Supabase/PostgreSQL)

## Core / System

| Table | Description |
|-------|-------------|
| `alembic_version` | Database migration tracking |
| `tenants` | Multi-tenant organizations |
| `users` | User accounts and authentication |

## Conversations & Messages

| Table | Description |
|-------|-------------|
| `conversations` | Chat/conversation sessions |
| `messages` | Individual messages within conversations |
| `email_conversations` | Email thread tracking |
| `calls` | Voice call records |
| `call_summaries` | AI-generated call summaries |

## Contacts & Leads

| Table | Description |
|-------|-------------|
| `contacts` | Customer contact records |
| `contact_aliases` | Alternative identifiers for contacts (email, phone) |
| `contact_merge_logs` | History of merged contacts |
| `leads` | Lead/prospect records |

## Notifications & Escalation

| Table | Description |
|-------|-------------|
| `notifications` | System notifications |
| `escalations` | Escalated issues requiring attention |

## Prompts & Configuration

| Table | Description |
|-------|-------------|
| `prompt_bundles` | Grouped prompt configurations |
| `prompt_sections` | Individual prompt sections |
| `config_snapshots` | Configuration version snapshots |
| `tenant_prompt_configs` | Per-tenant prompt settings |
| `tenant_widget_configs` | Per-tenant chat widget settings |

## Tenant Channel Configs

| Table | Description |
|-------|-------------|
| `tenant_sms_configs` | SMS/Twilio configuration per tenant |
| `tenant_email_configs` | Email/Gmail configuration per tenant |
| `tenant_voice_configs` | Voice/Telnyx configuration per tenant |
| `tenant_customer_service_configs` | Customer service integration settings |

## Business Profile & Scraping

| Table | Description |
|-------|-------------|
| `tenant_business_profiles` | Business info for AI context |

## Integrations

| Table | Description |
|-------|-------------|
| `jackrabbit_customers` | Jackrabbit CRM customer cache |
| `zapier_requests` | Zapier webhook request logs |
| `sms_opt_ins` | SMS marketing consent records |

---

## Foreign Key Dependencies

When truncating/deleting data, be aware of these key relationships:

- `leads` references `conversations`
- `messages` references `conversations`
- `email_conversations` references `leads`
- `calls` references `leads`
- `contact_aliases` references `contacts`
- `contact_merge_logs` references `contacts`
- `users` may reference `contacts` and `tenants`

**Safe truncation order for clearing conversation data:**
```sql
TRUNCATE messages, email_conversations, calls, call_summaries, leads, conversations CASCADE;
```

**Safe truncation for contacts only:**
```sql
TRUNCATE contact_aliases, contact_merge_logs, contacts CASCADE;
```
