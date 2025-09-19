"""add unique indexes to channels

Revision ID: 0008_unique_channels_indexes
Revises: 0007_create_workspaces_and_aux_tables
Create Date: 2025-09-12 00:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0008_unique_channels_indexes'
down_revision = '0007_create_workspaces_and_aux_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unique composite on (org_id, phone_number) when phone_number is not null
    op.execute(
        """
        DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'uq_channels_org_phone' AND n.nspname = 'public'
        ) THEN
            CREATE UNIQUE INDEX uq_channels_org_phone ON channels (org_id, phone_number) WHERE phone_number IS NOT NULL;
        END IF;
        END $$;
        """
    )

    # Unique expression index on (org_id, credentials->>'phone_number_id') when present
    op.execute(
        """
        DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'uq_channels_org_pnid' AND n.nspname = 'public'
        ) THEN
            CREATE UNIQUE INDEX uq_channels_org_pnid ON channels (org_id, ((credentials->>'phone_number_id'))) WHERE (credentials->>'phone_number_id') IS NOT NULL;
        END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_channels_org_pnid;")
    op.execute("DROP INDEX IF EXISTS uq_channels_org_phone;")

