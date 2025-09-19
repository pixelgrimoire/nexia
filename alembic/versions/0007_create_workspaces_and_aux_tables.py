"""create workspaces, workspace_members, notes, attachments, audit_logs

Revision ID: 0007_create_workspaces_and_aux_tables
Revises: 0006_create_flow_runs
Create Date: 2025-09-12 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0007_create_workspaces_and_aux_tables'
down_revision = '0006_create_flow_runs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workspaces
    op.create_table(
        'workspaces',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
    )

    # workspace_members
    op.create_table(
        'workspace_members',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('workspace_id', sa.String(), sa.ForeignKey('workspaces.id')),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id')),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
    )

    # notes
    op.create_table(
        'notes',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id')),
        sa.Column('author', sa.String()),
        sa.Column('body', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    # attachments
    op.create_table(
        'attachments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id')),
        sa.Column('url', sa.Text()),
        sa.Column('filename', sa.String()),
        sa.Column('uploaded_by', sa.String()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('storage_key', sa.String()),
    )

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('actor', sa.String()),
        sa.Column('action', sa.String()),
        sa.Column('entity_type', sa.String()),
        sa.Column('entity_id', sa.String()),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('attachments')
    op.drop_table('notes')
    op.drop_table('workspace_members')
    op.drop_table('workspaces')

