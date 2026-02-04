"""Add forum tables for cross-tenant discussion

Creates tables for user groups, forums, categories, posts, and votes.
These tables operate outside RLS since forums are cross-tenant by design.

Revision ID: add_forum_tables
Revises: add_admin_notification_tracking
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_forum_tables'
down_revision: Union[str, None] = 'add_customers_and_support_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_groups table
    op.create_table(
        'user_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('mapping_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug'),
        sa.UniqueConstraint('mapping_number')
    )
    op.create_index('ix_user_groups_id', 'user_groups', ['id'])

    # Create user_group_memberships table
    op.create_table(
        'user_group_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(50), server_default='member', nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['user_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'group_id', name='uq_user_group')
    )
    op.create_index('ix_user_group_memberships_id', 'user_group_memberships', ['id'])
    op.create_index('ix_user_group_memberships_user_id', 'user_group_memberships', ['user_id'])
    op.create_index('ix_user_group_memberships_group_id', 'user_group_memberships', ['group_id'])

    # Create forums table
    op.create_table(
        'forums',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['user_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index('ix_forums_id', 'forums', ['id'])
    op.create_index('ix_forums_slug', 'forums', ['slug'])

    # Create forum_categories table
    op.create_table(
        'forum_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('forum_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('allows_voting', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('admin_only_posting', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['forum_id'], ['forums.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('forum_id', 'slug', name='uq_forum_category_slug')
    )
    op.create_index('ix_forum_categories_id', 'forum_categories', ['id'])
    op.create_index('ix_forum_categories_forum_id', 'forum_categories', ['forum_id'])

    # Create forum_posts table
    op.create_table(
        'forum_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('author_user_id', sa.Integer(), nullable=False),
        sa.Column('author_tenant_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('vote_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_pinned', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.Column('archived_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['forum_categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['archived_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_forum_posts_id', 'forum_posts', ['id'])
    op.create_index('ix_forum_posts_category_id', 'forum_posts', ['category_id'])
    op.create_index('ix_forum_posts_author_user_id', 'forum_posts', ['author_user_id'])
    op.create_index('ix_forum_posts_status', 'forum_posts', ['status'])
    op.create_index('ix_forum_posts_created_at', 'forum_posts', ['created_at'])

    # Create forum_votes table
    op.create_table(
        'forum_votes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['forum_posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_vote')
    )
    op.create_index('ix_forum_votes_id', 'forum_votes', ['id'])
    op.create_index('ix_forum_votes_post_id', 'forum_votes', ['post_id'])
    op.create_index('ix_forum_votes_user_id', 'forum_votes', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_forum_votes_user_id', table_name='forum_votes')
    op.drop_index('ix_forum_votes_post_id', table_name='forum_votes')
    op.drop_index('ix_forum_votes_id', table_name='forum_votes')
    op.drop_table('forum_votes')

    op.drop_index('ix_forum_posts_created_at', table_name='forum_posts')
    op.drop_index('ix_forum_posts_status', table_name='forum_posts')
    op.drop_index('ix_forum_posts_author_user_id', table_name='forum_posts')
    op.drop_index('ix_forum_posts_category_id', table_name='forum_posts')
    op.drop_index('ix_forum_posts_id', table_name='forum_posts')
    op.drop_table('forum_posts')

    op.drop_index('ix_forum_categories_forum_id', table_name='forum_categories')
    op.drop_index('ix_forum_categories_id', table_name='forum_categories')
    op.drop_table('forum_categories')

    op.drop_index('ix_forums_slug', table_name='forums')
    op.drop_index('ix_forums_id', table_name='forums')
    op.drop_table('forums')

    op.drop_index('ix_user_group_memberships_group_id', table_name='user_group_memberships')
    op.drop_index('ix_user_group_memberships_user_id', table_name='user_group_memberships')
    op.drop_index('ix_user_group_memberships_id', table_name='user_group_memberships')
    op.drop_table('user_group_memberships')

    op.drop_index('ix_user_groups_id', table_name='user_groups')
    op.drop_table('user_groups')
