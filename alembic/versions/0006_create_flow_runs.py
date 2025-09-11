"""create flow_runs table

Revision ID: 0006_create_flow_runs
Revises: 0005_unique_messages_client_id
Create Date: 2025-09-11 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0006_create_flow_runs'
down_revision = '0005_unique_messages_client_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'flow_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('flow_id', sa.String(), sa.ForeignKey('flows.id')),
        sa.Column('status', sa.String()),
        sa.Column('last_step', sa.String()),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('flow_runs')

