# Tenant Prompt Isolation

This document explains how ChatterCheatah ensures complete data isolation between tenants for prompt bundles.

## Overview

ChatterCheatah is a **multi-tenant SaaS platform** where each customer (tenant) has their own isolated data. The prompt system uses a combination of database constraints and application logic to ensure that:

1. Each tenant's prompts are completely isolated from other tenants
2. Tenants can customize prompts without affecting others
3. A global base prompt provides consistent defaults across all tenants
4. Data integrity is enforced at the database level

## Database Schema

### PromptBundle Table

```sql
CREATE TABLE prompt_bundles (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id),  -- NULL = global
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    is_active BOOLEAN NOT NULL DEFAULT false,
    published_at TIMESTAMP,
    source_bundle_id INTEGER REFERENCES prompt_bundles(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- CONSTRAINTS FOR TENANT ISOLATION
    CONSTRAINT uq_prompt_bundles_tenant_name_version
        UNIQUE (tenant_id, name, version),

    -- Partial unique index: only one PRODUCTION bundle per tenant
    CONSTRAINT uq_prompt_bundles_tenant_production
        UNIQUE (tenant_id, status)
        WHERE status = 'production'
);
```

## Isolation Guarantees

### 1. Unique Name/Version Per Tenant

The `uq_prompt_bundles_tenant_name_version` constraint ensures:

```python
# ✓ ALLOWED: Different tenants with same prompt name/version
tenant_1 = create_prompt(tenant_id=1, name="Customer Service", version="1.0.0")
tenant_2 = create_prompt(tenant_id=2, name="Customer Service", version="1.0.0")

# ✗ BLOCKED: Same tenant, duplicate name/version
tenant_1_v1 = create_prompt(tenant_id=1, name="Customer Service", version="1.0.0")
tenant_1_v1_dupe = create_prompt(tenant_id=1, name="Customer Service", version="1.0.0")
# ^ Raises: IntegrityError (unique constraint violation)
```

### 2. One Production Bundle Per Tenant

The `uq_prompt_bundles_tenant_production` partial index ensures:

```python
# ✓ ALLOWED: Publish first prompt to production
publish_bundle(tenant_id=1, bundle_id=100)  # Sets status='production'

# ✗ BLOCKED: Try to publish a second prompt
publish_bundle(tenant_id=1, bundle_id=101)  # Already have production bundle!
# ^ Raises: IntegrityError (unique constraint violation)

# ✓ SOLUTION: Demote current production to draft first
set_status(tenant_id=1, bundle_id=100, status='draft')
publish_bundle(tenant_id=1, bundle_id=101)  # Now it works
```

### 3. Multiple Versions Allowed

Tenants can maintain multiple versions of their prompts:

```python
# ✓ ALLOWED: Same tenant, different versions
v1 = create_prompt(tenant_id=1, name="Customer Service", version="1.0.0")
v2 = create_prompt(tenant_id=1, name="Customer Service", version="2.0.0")
v3 = create_prompt(tenant_id=1, name="Customer Service", version="3.0.0")
```

### 4. Global vs Tenant Isolation

Global prompts (`tenant_id=NULL`) are isolated from tenant prompts:

```python
# ✓ ALLOWED: Global and tenant can have same name/version
global_prompt = create_prompt(tenant_id=None, name="Base", version="1.0.0")
tenant_prompt = create_prompt(tenant_id=1, name="Base", version="1.0.0")
```

## How Prompts Are Composed

When a customer interacts with the system, their prompt is composed from:

1. **Global Base Prompt** (tenant_id=NULL, status='production')
   - Provides foundational customer service behavior
   - Defines personality, tone, communication guidelines
   - Shared across ALL tenants

2. **Tenant-Specific Sections** (tenant_id=X, status='production')
   - Business information (hours, location, services)
   - Pricing details
   - FAQs
   - Custom instructions

**Example composition:**

```python
from app.domain.services.prompt_service import PromptService

async def get_composed_prompt(tenant_id: int):
    prompt_service = PromptService(db)

    # Automatically merges global + tenant sections
    final_prompt = await prompt_service.compose_prompt(tenant_id)

    return final_prompt
```

Result for Tenant #1 (Swim School):
```
You are a professional customer service assistant... (GLOBAL BASE)

PERSONALITY AND TONE:
- Be friendly, professional, and approachable... (GLOBAL BASE)

SWIM SCHOOL EXPERTISE:
- Understand age groups: parent-tot, preschool... (TENANT CUSTOM)

BUSINESS INFORMATION:
Name: Happy Swimmers Swim School
Hours: Mon-Fri 9am-8pm, Sat 9am-5pm
Location: 123 Pool Lane, Miami, FL... (TENANT BUSINESS_INFO)

PRICING:
- Group lessons: $120/month
- Private lessons: $50/session... (TENANT PRICING)

FAQ:
Q: What should my child bring?
A: Swimsuit, towel, goggles... (TENANT FAQ)
```

## Migration Guide

### Step 1: Run the Migration

```bash
# Apply the tenant isolation constraints
.venv/bin/alembic upgrade head
```

### Step 2: Verify Existing Data

If you have existing data, check for conflicts:

```sql
-- Find tenants with duplicate name/version
SELECT tenant_id, name, version, COUNT(*)
FROM prompt_bundles
GROUP BY tenant_id, name, version
HAVING COUNT(*) > 1;

-- Find tenants with multiple production bundles
SELECT tenant_id, COUNT(*)
FROM prompt_bundles
WHERE status = 'production'
GROUP BY tenant_id
HAVING COUNT(*) > 1;
```

### Step 3: Clean Up Conflicts (If Any)

```python
# Example: Keep only the most recent production bundle
async def fix_multiple_production():
    repo = PromptRepository(db)

    # Get all tenants with multiple production bundles
    conflicts = await db.execute("""
        SELECT tenant_id, array_agg(id ORDER BY published_at DESC) as bundle_ids
        FROM prompt_bundles
        WHERE status = 'production'
        GROUP BY tenant_id
        HAVING COUNT(*) > 1
    """)

    for tenant_id, bundle_ids in conflicts:
        # Keep the first (most recent), demote the rest
        for bundle_id in bundle_ids[1:]:
            await repo.set_status(tenant_id, bundle_id, 'draft')
```

## Testing

Run the isolation test suite:

```bash
uv run python scripts/test_tenant_prompt_isolation.py
```

This verifies:
- ✓ Different tenants can have prompts with the same name/version
- ✓ Same tenant cannot have duplicate name/version combinations
- ✓ Same tenant can have multiple versions of the same prompt
- ✓ Each tenant can only have ONE production bundle at a time
- ✓ Global prompts are isolated from tenant prompts

## API Examples

### Creating Tenant-Specific Prompts

```python
from app.persistence.repositories.prompt_repository import PromptRepository

async def create_tenant_prompt(tenant_id: int):
    repo = PromptRepository(db)

    # Create a new prompt bundle for the tenant
    bundle = await repo.create(
        tenant_id=tenant_id,
        name="Customer Service Prompt",
        version="1.0.0",
        status="draft"
    )

    # Add business info section
    business_section = PromptSection(
        bundle_id=bundle.id,
        section_key="business_info",
        scope="business_info",
        content="""
        BUSINESS INFORMATION:
        Name: Acme Swim School
        Hours: Mon-Fri 9am-8pm
        Location: 123 Main St
        """,
        order=10
    )
    db.add(business_section)

    # Add pricing section
    pricing_section = PromptSection(
        bundle_id=bundle.id,
        section_key="pricing",
        scope="pricing",
        content="""
        PRICING:
        - Group lessons: $120/month
        - Private lessons: $50/session
        """,
        order=20
    )
    db.add(pricing_section)

    await db.commit()

    # Publish to production
    await repo.publish_bundle(tenant_id, bundle.id)
```

### Querying Prompts

```python
# Get the active production prompt for a tenant
bundle = await repo.get_production_bundle(tenant_id=1)

# List all prompts for a tenant
bundles = await repo.list(tenant_id=1)

# Get the global base prompt
global_bundle = await repo.get_global_base_bundle()
```

## Security Considerations

### Tenant ID Must Always Be Checked

The repository pattern enforces tenant scoping:

```python
# ✓ SAFE: Repository enforces tenant_id
bundle = await repo.get_by_id(tenant_id=current_user.tenant_id, id=100)

# ✗ DANGEROUS: Never query without tenant_id check
bundle = await db.query(PromptBundle).filter(PromptBundle.id == 100).first()
# ^ Could return another tenant's data!
```

### API Endpoints Must Validate Tenant Access

```python
@router.get("/prompts/{bundle_id}")
async def get_prompt(
    bundle_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = PromptRepository(db)

    # This will return None if bundle doesn't belong to user's tenant
    bundle = await repo.get_by_id(current_user.tenant_id, bundle_id)

    if not bundle:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return bundle
```

## Performance Considerations

### Indexes

The following indexes optimize tenant-scoped queries:

```sql
-- Primary lookup by tenant
CREATE INDEX ix_prompt_bundles_tenant_id ON prompt_bundles(tenant_id);

-- Composite index for common query patterns
CREATE INDEX ix_prompt_bundles_tenant_status
    ON prompt_bundles(tenant_id, status);
```

### Query Patterns

```python
# ✓ EFFICIENT: Uses tenant_id index
bundles = await repo.list(tenant_id=1, status='production')

# ✗ INEFFICIENT: Full table scan
bundles = await db.query(PromptBundle).filter(
    PromptBundle.name.like('%Customer%')
).all()

# ✓ BETTER: Add tenant_id filter
bundles = await db.query(PromptBundle).filter(
    PromptBundle.tenant_id == 1,
    PromptBundle.name.like('%Customer%')
).all()
```

## Troubleshooting

### Error: Duplicate key value violates unique constraint

```
IntegrityError: duplicate key value violates unique constraint
"uq_prompt_bundles_tenant_name_version"
```

**Cause:** Attempting to create a prompt with a name/version that already exists for this tenant.

**Solution:**
- Change the version number
- Or update the existing prompt instead of creating a new one

### Error: Cannot have multiple production bundles

```
IntegrityError: duplicate key value violates unique constraint
"uq_prompt_bundles_tenant_production"
```

**Cause:** Attempting to publish a second bundle when one is already in production.

**Solution:**
```python
# Demote current production to draft first
current_prod = await repo.get_production_bundle(tenant_id)
await repo.set_status(tenant_id, current_prod.id, 'draft')

# Now publish the new one
await repo.publish_bundle(tenant_id, new_bundle_id)
```

Or use the atomic `publish_bundle` method which handles this automatically:

```python
# This method demotes old production and promotes the new one atomically
await repo.publish_bundle(tenant_id, new_bundle_id)
```

## Summary

The tenant isolation system ensures:

| Feature | Implementation | Benefit |
|---------|---------------|---------|
| Data Isolation | `tenant_id` column + constraints | Each tenant's data is completely separate |
| Unique Prompts | `UNIQUE(tenant_id, name, version)` | No duplicate prompts per tenant |
| Single Production | Partial unique index on `status='production'` | Clean production environment |
| Global Base | `tenant_id=NULL` for platform defaults | Consistent baseline across tenants |
| Versioning | Multiple versions per name allowed | Safe iteration and rollback |

This architecture enables ChatterCheatah to:
- Scale to thousands of tenants safely
- Allow full customization per tenant
- Maintain data integrity at the database level
- Provide consistent defaults while enabling customization
