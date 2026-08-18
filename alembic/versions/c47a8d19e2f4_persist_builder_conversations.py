"""persist builder conversations

Revision ID: c47a8d19e2f4
Revises: aa8f2d91e730
"""

from alembic import op
import sqlalchemy as sa


revision = "c47a8d19e2f4"
down_revision = "aa8f2d91e730"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("chat_sessions", "user_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("chat_sessions", sa.Column("class_key", sa.String(length=40), nullable=True))
    op.add_column("chat_sessions", sa.Column("spec_key", sa.String(length=40), nullable=True))
    op.add_column("chat_sessions", sa.Column("state_json", sa.JSON(), nullable=True))
    op.add_column("chat_sessions", sa.Column("agent_state_json", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("chat_sessions", "agent_state_json")
    op.drop_column("chat_sessions", "state_json")
    op.drop_column("chat_sessions", "spec_key")
    op.drop_column("chat_sessions", "class_key")
    op.alter_column("chat_sessions", "user_id", existing_type=sa.BigInteger(), nullable=False)
