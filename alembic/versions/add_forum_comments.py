"""Add forum comments tables for Reddit-style replies

Creates forum_comments and forum_comment_votes tables for threaded
discussions with upvote/downvote support.

Revision ID: add_forum_comments
Revises: add_forum_tables
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_forum_comments'
down_revision: Union[str, None] = 'add_forum_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create forum_comments table
    op.create_table(
        'forum_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('parent_comment_id', sa.Integer(), nullable=True),  # For nested replies
        sa.Column('author_user_id', sa.Integer(), nullable=False),
        sa.Column('author_tenant_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), server_default='0', nullable=False),  # upvotes - downvotes
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['forum_posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_comment_id'], ['forum_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_forum_comments_id', 'forum_comments', ['id'])
    op.create_index('ix_forum_comments_post_id', 'forum_comments', ['post_id'])
    op.create_index('ix_forum_comments_parent_comment_id', 'forum_comments', ['parent_comment_id'])
    op.create_index('ix_forum_comments_author_user_id', 'forum_comments', ['author_user_id'])
    op.create_index('ix_forum_comments_created_at', 'forum_comments', ['created_at'])

    # Create forum_comment_votes table (supports upvote +1 and downvote -1)
    op.create_table(
        'forum_comment_votes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vote_value', sa.Integer(), nullable=False),  # +1 for upvote, -1 for downvote
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['forum_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('comment_id', 'user_id', name='uq_comment_vote')
    )
    op.create_index('ix_forum_comment_votes_id', 'forum_comment_votes', ['id'])
    op.create_index('ix_forum_comment_votes_comment_id', 'forum_comment_votes', ['comment_id'])
    op.create_index('ix_forum_comment_votes_user_id', 'forum_comment_votes', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_forum_comment_votes_user_id', table_name='forum_comment_votes')
    op.drop_index('ix_forum_comment_votes_comment_id', table_name='forum_comment_votes')
    op.drop_index('ix_forum_comment_votes_id', table_name='forum_comment_votes')
    op.drop_table('forum_comment_votes')

    op.drop_index('ix_forum_comments_created_at', table_name='forum_comments')
    op.drop_index('ix_forum_comments_author_user_id', table_name='forum_comments')
    op.drop_index('ix_forum_comments_parent_comment_id', table_name='forum_comments')
    op.drop_index('ix_forum_comments_post_id', table_name='forum_comments')
    op.drop_index('ix_forum_comments_id', table_name='forum_comments')
    op.drop_table('forum_comments')
