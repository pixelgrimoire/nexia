"""set server defaults for created_at columns

Revision ID: 0009_set_defaults_created_at
Revises: 0008_unique_channels_indexes
Create Date: 2025-09-12 00:15:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0009_set_defaults_created_at'
down_revision = '0008_unique_channels_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Set default NOW() where applicable
    for table, column in [
        ('users', 'created_at'),
        ('messages', 'created_at'),
        ('workspaces', 'created_at'),
        ('workspace_members', 'created_at'),
        ('notes', 'created_at'),
        ('attachments', 'created_at'),
        ('audit_logs', 'created_at'),
    ]:
        try:
            op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT NOW()"))
        except Exception:
            # tolerate when column/table doesn't exist in some envs
            pass


def downgrade() -> None:
    for table, column in [
        ('users', 'created_at'),
        ('messages', 'created_at'),
        ('workspaces', 'created_at'),
        ('workspace_members', 'created_at'),
        ('notes', 'created_at'),
        ('attachments', 'created_at'),
        ('audit_logs', 'created_at'),
    ]:
        try:
            op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"))
        except Exception:
            pass

