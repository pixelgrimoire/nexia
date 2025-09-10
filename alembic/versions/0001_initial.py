"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2025-09-10 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('plan', sa.String(), server_default='starter'),
        sa.Column('billing_status', sa.String(), server_default='trial'),
    )

    # users
    op.create_table(
        'users',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='active'),
    )

    # channels
    op.create_table(
        'channels',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('type', sa.String()),
        sa.Column('mode', sa.String()),
        sa.Column('status', sa.String()),
        sa.Column('credentials', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('phone_number', sa.String()),
    )

    # contacts
    op.create_table(
        'contacts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('wa_id', sa.String()),
        sa.Column('phone', sa.String()),
        sa.Column('name', sa.String()),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('tags', postgresql.ARRAY(sa.String())),
        sa.Column('consent', sa.String()),
        sa.Column('locale', sa.String()),
        sa.Column('timezone', sa.String()),
    )

    # conversations
    op.create_table(
        'conversations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('contact_id', sa.String(), sa.ForeignKey('contacts.id')),
        sa.Column('channel_id', sa.String(), sa.ForeignKey('channels.id')),
        sa.Column('state', sa.String()),
        sa.Column('assignee', sa.String()),
        sa.Column('last_activity_at', sa.DateTime()),
    )

    # messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id')),
        sa.Column('direction', sa.String()),
        sa.Column('type', sa.String()),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('template_id', sa.String(), nullable=True),
        sa.Column('status', sa.String()),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('client_id', sa.String()),
    )

    # templates
    op.create_table(
        'templates',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('name', sa.String()),
        sa.Column('language', sa.String()),
        sa.Column('category', sa.String()),
        sa.Column('body', sa.Text()),
        sa.Column('variables', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('status', sa.String()),
    )

    # flows
    op.create_table(
        'flows',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('org_id', sa.String(), sa.ForeignKey('organizations.id')),
        sa.Column('name', sa.String()),
        sa.Column('version', sa.Integer()),
        sa.Column('graph', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('status', sa.String()),
        sa.Column('created_by', sa.String()),
    )


def downgrade() -> None:
    op.drop_table('flows')
    op.drop_table('templates')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('contacts')
    op.drop_table('channels')
    op.drop_table('users')
    op.drop_table('organizations')

