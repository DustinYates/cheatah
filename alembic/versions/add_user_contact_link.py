"""Add user contact_id link

Revision ID: add_user_contact_link
Revises: add_widget_config
Create Date: 2025-12-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_user_contact_link'
down_revision = 'add_widget_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add contact_id column to users table
    op.add_column('users', sa.Column('contact_id', sa.Integer(), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'users_contact_id_fkey',
        'users', 'contacts',
        ['contact_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create index on contact_id
    op.create_index('ix_users_contact_id', 'users', ['contact_id'], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_users_contact_id', table_name='users')

    # Drop foreign key constraint
    op.drop_constraint('users_contact_id_fkey', 'users', type_='foreignkey')

    # Drop column
    op.drop_column('users', 'contact_id')
