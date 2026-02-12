"""add_voice_ab_testing

Revision ID: 373dd7474501
Revises: 7ff4aed92d20
Create Date: 2026-02-12 13:45:43.854430

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '373dd7474501'
down_revision: Union[str, None] = '7ff4aed92d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add voice variant tracking columns to calls table
    op.add_column('calls', sa.Column('assistant_id', sa.String(length=255), nullable=True))
    op.add_column('calls', sa.Column('voice_model', sa.String(length=255), nullable=True))
    op.create_index('ix_calls_assistant_id', 'calls', ['assistant_id'])
    op.create_index('ix_calls_voice_model', 'calls', ['voice_model'])
    op.create_index('ix_calls_tenant_voice_model', 'calls', ['tenant_id', 'voice_model'])

    # Create voice A/B tests table
    op.create_table(
        'voice_ab_tests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create voice A/B test variants table
    op.create_table(
        'voice_ab_test_variants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('test_id', sa.Integer(), sa.ForeignKey('voice_ab_tests.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('voice_model', sa.String(length=255), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('is_control', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('test_id', 'voice_model', name='uq_voice_ab_test_variant_model'),
    )

    # Enable RLS on new tables
    op.execute("ALTER TABLE voice_ab_tests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE voice_ab_test_variants ENABLE ROW LEVEL SECURITY")

    # RLS policies for voice_ab_tests
    op.execute("""
        CREATE POLICY voice_ab_tests_tenant_isolation ON voice_ab_tests
        USING (tenant_id = current_setting('app.current_tenant_id', true)::int)
    """)

    # RLS policy for voice_ab_test_variants (via join to voice_ab_tests)
    op.execute("""
        CREATE POLICY voice_ab_test_variants_tenant_isolation ON voice_ab_test_variants
        USING (test_id IN (
            SELECT id FROM voice_ab_tests
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::int
        ))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS voice_ab_test_variants_tenant_isolation ON voice_ab_test_variants")
    op.execute("DROP POLICY IF EXISTS voice_ab_tests_tenant_isolation ON voice_ab_tests")
    op.drop_table('voice_ab_test_variants')
    op.drop_table('voice_ab_tests')
    op.drop_index('ix_calls_tenant_voice_model', table_name='calls')
    op.drop_index('ix_calls_voice_model', table_name='calls')
    op.drop_index('ix_calls_assistant_id', table_name='calls')
    op.drop_column('calls', 'voice_model')
    op.drop_column('calls', 'assistant_id')
