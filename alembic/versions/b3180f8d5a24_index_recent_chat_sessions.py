"""index recent chat sessions

Revision ID: b3180f8d5a24
Revises: c47a8d19e2f4
"""

from alembic import op


revision = "b3180f8d5a24"
down_revision = "c47a8d19e2f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_chat_sessions_updated_at_id", "chat_sessions", ["updated_at", "id"])


def downgrade():
    op.drop_index("ix_chat_sessions_updated_at_id", table_name="chat_sessions")
