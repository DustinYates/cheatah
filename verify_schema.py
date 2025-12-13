#!/usr/bin/env python3
"""Script to verify Alembic migration status and database schema."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect, text
from app.settings import settings

def verify_schema():
    """Verify the database schema matches the migration."""
    
    # Convert async URL to sync for direct connection
    db_url = settings.database_url
    if "+asyncpg" in db_url.lower():
        db_url = db_url.replace("+asyncpg", "")
    
    print(f"Connecting to database...")
    print(f"URL prefix: {db_url[:50]}...")
    
    try:
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Check Alembic version table
            print("\n" + "="*60)
            print("1. Checking Alembic version table...")
            print("="*60)
            
            try:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                if version:
                    print(f"✅ Alembic current revision: {version}")
                else:
                    print("⚠️  Alembic version table exists but is empty")
            except Exception as e:
                print(f"❌ Error checking Alembic version: {e}")
                return False
            
            # List all tables
            print("\n" + "="*60)
            print("2. Checking database tables...")
            print("="*60)
            
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            expected_tables = {
                'tenants',
                'users', 
                'conversations',
                'messages',
                'leads',
                'prompt_bundles',
                'prompt_sections',
                'alembic_version'  # Alembic's own table
            }
            
            print(f"\nFound {len(tables)} tables in database:")
            for table in sorted(tables):
                marker = "✅" if table in expected_tables else "⚠️ "
                print(f"  {marker} {table}")
            
            # Check if all expected tables exist
            missing_tables = expected_tables - set(tables)
            if missing_tables:
                print(f"\n❌ Missing tables: {missing_tables}")
                return False
            else:
                print(f"\n✅ All expected tables are present!")
            
            # Check indexes for each table
            print("\n" + "="*60)
            print("3. Checking indexes...")
            print("="*60)
            
            table_indexes = {
                'tenants': ['ix_tenants_id', 'ix_tenants_subdomain'],
                'users': ['ix_users_id', 'ix_users_tenant_id', 'ix_users_email'],
                'conversations': ['ix_conversations_id', 'ix_conversations_tenant_id', 'ix_conversations_external_id'],
                'messages': ['ix_messages_id', 'ix_messages_conversation_id', 'ix_messages_sequence_number'],
                'leads': ['ix_leads_id', 'ix_leads_tenant_id', 'ix_leads_conversation_id', 'ix_leads_email', 'ix_leads_phone'],
                'prompt_bundles': ['ix_prompt_bundles_id', 'ix_prompt_bundles_tenant_id'],
                'prompt_sections': ['ix_prompt_sections_id', 'ix_prompt_sections_bundle_id']
            }
            
            all_indexes_present = True
            for table_name, expected_indexes in table_indexes.items():
                indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
                missing = set(expected_indexes) - set(indexes)
                if missing:
                    print(f"  ⚠️  {table_name}: Missing indexes {missing}")
                    all_indexes_present = False
                else:
                    print(f"  ✅ {table_name}: All {len(expected_indexes)} indexes present")
            
            if not all_indexes_present:
                print("\n⚠️  Some indexes are missing")
            else:
                print("\n✅ All expected indexes are present!")
            
            return True
            
    except Exception as e:
        print(f"\n❌ Error connecting to database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_schema()
    sys.exit(0 if success else 1)

