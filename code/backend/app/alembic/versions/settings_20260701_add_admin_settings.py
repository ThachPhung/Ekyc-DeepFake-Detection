"""Add admin settings

Revision ID: settings20260701
Revises: notify20260701
Create Date: 2026-07-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "settings20260701"
down_revision = "notify20260701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_settings",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("admin_settings")
