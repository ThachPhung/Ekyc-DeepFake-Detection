"""Add email verification to user

Revision ID: a3c9f2d4e5b6
Revises: 6f7a8b9c0d12
Create Date: 2026-06-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a3c9f2d4e5b6"
down_revision = "6f7a8b9c0d12"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("user", "is_email_verified", server_default=None)


def downgrade():
    op.drop_column("user", "is_email_verified")
