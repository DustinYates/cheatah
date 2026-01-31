# Chatbot Session Context

## Project Overview
**ChatterCheetah** - Multi-tenant AI assistant platform for voice, SMS, email, and web chat.

## Current Issue
The **web chatbot** is capturing wrong information for names. Example: "Fitness Langham" (a location name) is being saved as a lead name instead of the actual person's name.

**Screenshot reference:** Dashboard showing "Fitness Langham" as a lead name with no email/phone - this is a location, not a person.

---

## Infrastructure

### Cloud Run (Backend)
- **Service:** `chattercheatah`
- **URL:** https://chattercheatah-900139201687.us-central1.run.app
- **Project:** `chatbots-466618`
- **Region:** `us-central1`

### Database (Supabase PostgreSQL)
- **Connection:** Stored in GCP Secret `database-url`
- **Access:** `gcloud secrets versions access latest --secret=database-url`
- **Driver:** `postgresql+asyncpg://`

### Key Environment Variables (in Cloud Run)
```
ENVIRONMENT=production
GCP_PROJECT_ID=chatbots-466618
GCP_REGION=us-central1
GEMINI_MODEL=gemini-3-flash-preview
DATABASE_URL=(secret)
JWT_SECRET_KEY=(secret)
GEMINI_API_KEY=(secret)
```

---

## Relevant Files for Chatbot

### Chat/Widget Routes
- `app/api/routes/chat_widget.py` - Widget chat endpoints
- `app/api/routes/chatbot.py` - Chatbot API routes (if exists)

### Services
- `app/domain/services/chat_service.py` - Chat processing logic
- `app/domain/services/prompt_service.py` - Prompt composition (includes `compose_prompt_chat()`)

### Models
- `app/persistence/models/conversation.py` - Conversation/Message models
- `app/persistence/models/lead.py` - Lead model (where names are stored)
- `app/persistence/models/contact.py` - Contact model

### Frontend
- `client/src/` - React frontend
- Widget embed code serves from the backend

---

## Current Tenant for Testing
- **Tenant ID:** 3
- **Name:** BSS Cypress-Spring (British Swim Schools)
- **Telnyx Number:** +12816990999

---

## Recent Changes (This Session)

1. **Voice Prompt Transformer** - Created `app/domain/services/voice_prompt_transformer.py`
   - Wraps chat prompts in voice-safe rules for Telnyx AI Assistant
   - Cleans markdown, URLs, emails from prompts

2. **Fallback Voice Prompt** - Added `fallback_voice_prompt` column to `tenant_voice_configs`
   - Tenant-specific backup prompt if dynamic fails

3. **Stacking Names/Emails** - Modified `telnyx_webhooks.py` to append multiple names/emails
   - When multiple callers use same phone, names stack: "Name1, Name2"

---

## Problem to Solve Next Session

**Chatbot is extracting wrong entity as "name"**

The chatbot appears to be:
1. Extracting location names (like "Fitness Langham") instead of person names
2. Creating leads with incorrect name data
3. Possibly using entity extraction that's too aggressive

**Investigation areas:**
1. How does the chatbot extract contact info from messages?
2. Where is the lead creation logic for chat?
3. Is there entity extraction/NER being used?
4. What prompt instructions guide the chatbot's data extraction?

---

## Useful Commands

```bash
# Deploy backend
cd /Users/dustinyates/Desktop/chattercheetah
gcloud run deploy chattercheatah --source . --region us-central1 --allow-unauthenticated

# Run migrations
source .venv/bin/activate
PROD_DB_URL=$(gcloud secrets versions access latest --secret=database-url)
# Then use alembic or direct SQL

# Check logs
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="chattercheatah"' --limit 20

# Build frontend
cd client && npm run build
```

---

## Database Quick Access

```python
# Connect to production DB
PROD_DB_URL=$(gcloud secrets versions access latest --secret=database-url)
source .venv/bin/activate
python3 -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def query():
    url = '$PROD_DB_URL'.replace('postgresql://', 'postgresql+asyncpg://')
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        result = await conn.execute(text('SELECT * FROM leads LIMIT 5'))
        for row in result:
            print(row)
    await engine.dispose()

asyncio.run(query())
"
```
