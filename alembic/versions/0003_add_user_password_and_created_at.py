"""add user password_hash and created_at

Revision ID: 0003_add_user_password_and_created_at
Revises: 0002_add_created_at_messages
Create Date: 2025-09-10 00:00:02

"""
from alembic import op
import sqlalchemy as sa


revision = '0003_add_user_password_and_created_at'
down_revision = '0002_add_created_at_messages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String()))
    op.add_column('users', sa.Column('created_at', sa.DateTime()))


def downgrade() -> None:
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'password_hash')

