"""add created_at to messages

Revision ID: 0002_add_created_at_messages
Revises: 0001_initial
Create Date: 2025-09-10 00:00:01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0002_add_created_at_messages'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_at with server default now() for Postgres; SQLite will ignore server_default on existing rows
    op.add_column('messages', sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')))


def downgrade() -> None:
    op.drop_column('messages', 'created_at')

