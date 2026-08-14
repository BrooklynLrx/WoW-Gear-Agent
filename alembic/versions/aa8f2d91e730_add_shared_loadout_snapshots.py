"""add shared loadout snapshots

Revision ID: aa8f2d91e730
Revises: 6d7a2f91c4b3
"""

from alembic import op
import sqlalchemy as sa


revision = "aa8f2d91e730"
down_revision = "6d7a2f91c4b3"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("loadouts", "user_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column(
        "loadouts",
        sa.Column("creator_name", sa.String(length=64), server_default="unknown", nullable=False),
    )
    op.add_column("loadouts", sa.Column("class_key", sa.String(length=40), nullable=True))
    op.add_column("loadouts", sa.Column("spec_key", sa.String(length=40), nullable=True))
    op.add_column("loadouts", sa.Column("state_json", sa.JSON(), nullable=True))
    op.create_index("ix_loadouts_creator_name", "loadouts", ["creator_name"])


def downgrade():
    op.drop_index("ix_loadouts_creator_name", table_name="loadouts")
    op.drop_column("loadouts", "state_json")
    op.drop_column("loadouts", "spec_key")
    op.drop_column("loadouts", "class_key")
    op.drop_column("loadouts", "creator_name")
    op.alter_column("loadouts", "user_id", existing_type=sa.BigInteger(), nullable=False)
