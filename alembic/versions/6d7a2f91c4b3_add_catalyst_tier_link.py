"""add catalyst tier source link

Revision ID: 6d7a2f91c4b3
Revises: f4b11843e38e
"""

from alembic import op
import sqlalchemy as sa


revision = "6d7a2f91c4b3"
down_revision = "f4b11843e38e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("loadout_items", sa.Column("catalyst_tier_item_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_loadout_items_catalyst_tier_item",
        "loadout_items", "items",
        ["catalyst_tier_item_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_loadout_items_catalyst_tier_item", "loadout_items", type_="foreignkey")
    op.drop_column("loadout_items", "catalyst_tier_item_id")
