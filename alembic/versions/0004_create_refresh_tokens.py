"""create refresh_tokens table

Revision ID: 0004_create_refresh_tokens
Revises: 0003_add_user_password_and_created_at
Create Date: 2025-09-10 00:00:03

"""
from alembic import op
import sqlalchemy as sa


revision = '0004_create_refresh_tokens'
down_revision = '0003_add_user_password_and_created_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id')),
        sa.Column('token', sa.String()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('revoked', sa.String(), server_default='false')
    )


def downgrade() -> None:
    op.drop_table('refresh_tokens')

