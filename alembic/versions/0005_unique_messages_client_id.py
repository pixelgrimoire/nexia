"""add unique index on messages (conversation_id, client_id) and dedupe

Revision ID: 0005_unique_messages_client_id
Revises: 0004_create_refresh_tokens
Create Date: 2025-09-10 00:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0005_unique_messages_client_id'
down_revision = '0004_create_refresh_tokens'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deduplicate existing rows where (conversation_id, client_id) repeats (client_id not null)
    op.execute(
        """
        WITH d AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY conversation_id, client_id
                       ORDER BY COALESCE(created_at, NOW()), id
                   ) AS rn
            FROM messages
            WHERE client_id IS NOT NULL
        )
        DELETE FROM messages m
        USING d
        WHERE m.id = d.id AND d.rn > 1;
        """
    )

    # Partial unique index to enforce uniqueness only when client_id is not null
    op.create_index(
        'uq_messages_conv_client',
        'messages',
        ['conversation_id', 'client_id'],
        unique=True,
        postgresql_where=sa.text('client_id IS NOT NULL')
    )


def downgrade() -> None:
    op.drop_index('uq_messages_conv_client', table_name='messages')

