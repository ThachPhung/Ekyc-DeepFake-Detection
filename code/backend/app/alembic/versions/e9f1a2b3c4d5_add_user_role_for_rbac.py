"""add user role for rbac

Revision ID: e9f1a2b3c4d5
Revises: d4e5f6a7b8c9
Create Date: 2026-06-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e9f1a2b3c4d5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
    )
    op.create_index(op.f("ix_user_role"), "user", ["role"], unique=False)
    op.alter_column("user", "role", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_role"), table_name="user")
    op.drop_column("user", "role")
