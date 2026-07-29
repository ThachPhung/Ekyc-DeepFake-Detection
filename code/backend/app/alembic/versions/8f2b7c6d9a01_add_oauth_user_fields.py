"""Add OAuth user fields

Revision ID: 8f2b7c6d9a01
Revises: 2f4c8a9d7b1e
Create Date: 2026-06-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "8f2b7c6d9a01"
down_revision = "2f4c8a9d7b1e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("auth_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("provider_user_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_user_auth_provider"), "user", ["auth_provider"], unique=False)
    op.create_index(
        op.f("ix_user_provider_user_id"),
        "user",
        ["provider_user_id"],
        unique=False,
    )
    op.alter_column(
        "user",
        "hashed_password",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "user",
        "hashed_password",
        existing_type=sa.String(),
        nullable=False,
    )
    op.drop_index(op.f("ix_user_provider_user_id"), table_name="user")
    op.drop_index(op.f("ix_user_auth_provider"), table_name="user")
    op.drop_column("user", "updated_at")
    op.drop_column("user", "provider_user_id")
    op.drop_column("user", "auth_provider")
    op.drop_column("user", "avatar_url")
