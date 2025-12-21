"""Add contact merge and soft delete support

Revision ID: add_contact_merge_delete
Revises: add_contacts_table
Create Date: 2025-12-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_contact_merge_delete'
down_revision = 'add_contacts_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add soft delete columns to contacts table
    op.add_column('contacts', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('contacts', sa.Column('deleted_by', sa.Integer(), nullable=True))
    
    # Add merge tracking columns to contacts table
    op.add_column('contacts', sa.Column('merged_into_contact_id', sa.Integer(), nullable=True))
    op.add_column('contacts', sa.Column('merged_at', sa.DateTime(), nullable=True))
    op.add_column('contacts', sa.Column('merged_by', sa.Integer(), nullable=True))
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_contacts_deleted_by_users',
        'contacts', 'users',
        ['deleted_by'], ['id']
    )
    op.create_foreign_key(
        'fk_contacts_merged_into_contact',
        'contacts', 'contacts',
        ['merged_into_contact_id'], ['id']
    )
    op.create_foreign_key(
        'fk_contacts_merged_by_users',
        'contacts', 'users',
        ['merged_by'], ['id']
    )
    
    # Create contact_aliases table for storing secondary identifiers
    op.create_table(
        'contact_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=False),
        sa.Column('alias_type', sa.String(length=50), nullable=False),  # email, phone, name
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('is_primary', sa.Boolean(), default=False, nullable=False),
        sa.Column('source_contact_id', sa.Integer(), nullable=True),  # Original contact this came from
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_contact_aliases_contact_id', 'contact_aliases', ['contact_id'])
    op.create_index('ix_contact_aliases_type_value', 'contact_aliases', ['alias_type', 'value'])
    
    # Create contact_merge_logs table for audit trail
    op.create_table(
        'contact_merge_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('primary_contact_id', sa.Integer(), nullable=False),
        sa.Column('secondary_contact_id', sa.Integer(), nullable=False),
        sa.Column('merged_by', sa.Integer(), nullable=False),
        sa.Column('merged_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('field_resolutions', sa.JSON(), nullable=True),  # Which fields were chosen from where
        sa.Column('secondary_data_snapshot', sa.JSON(), nullable=True),  # Backup of secondary contact data
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['primary_contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['secondary_contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merged_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_contact_merge_logs_tenant_id', 'contact_merge_logs', ['tenant_id'])
    op.create_index('ix_contact_merge_logs_primary_contact_id', 'contact_merge_logs', ['primary_contact_id'])
    
    # Add contact_id to leads table for direct contact association (after merge)
    op.add_column('leads', sa.Column('contact_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_leads_contact_id',
        'leads', 'contacts',
        ['contact_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_leads_contact_id', 'leads', ['contact_id'])
    
    # Add contact_id to conversations table for direct contact association
    op.add_column('conversations', sa.Column('contact_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_conversations_contact_id',
        'conversations', 'contacts',
        ['contact_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_conversations_contact_id', 'conversations', ['contact_id'])


def downgrade() -> None:
    # Drop indexes and foreign keys from conversations
    op.drop_index('ix_conversations_contact_id', table_name='conversations')
    op.drop_constraint('fk_conversations_contact_id', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'contact_id')
    
    # Drop indexes and foreign keys from leads
    op.drop_index('ix_leads_contact_id', table_name='leads')
    op.drop_constraint('fk_leads_contact_id', 'leads', type_='foreignkey')
    op.drop_column('leads', 'contact_id')
    
    # Drop contact_merge_logs table
    op.drop_index('ix_contact_merge_logs_primary_contact_id', table_name='contact_merge_logs')
    op.drop_index('ix_contact_merge_logs_tenant_id', table_name='contact_merge_logs')
    op.drop_table('contact_merge_logs')
    
    # Drop contact_aliases table
    op.drop_index('ix_contact_aliases_type_value', table_name='contact_aliases')
    op.drop_index('ix_contact_aliases_contact_id', table_name='contact_aliases')
    op.drop_table('contact_aliases')
    
    # Drop merge tracking columns from contacts
    op.drop_constraint('fk_contacts_merged_by_users', 'contacts', type_='foreignkey')
    op.drop_constraint('fk_contacts_merged_into_contact', 'contacts', type_='foreignkey')
    op.drop_constraint('fk_contacts_deleted_by_users', 'contacts', type_='foreignkey')
    op.drop_column('contacts', 'merged_by')
    op.drop_column('contacts', 'merged_at')
    op.drop_column('contacts', 'merged_into_contact_id')
    op.drop_column('contacts', 'deleted_by')
    op.drop_column('contacts', 'deleted_at')
