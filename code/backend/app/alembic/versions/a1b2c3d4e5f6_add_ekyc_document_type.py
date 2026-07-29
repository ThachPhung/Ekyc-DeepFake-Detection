"""Add eKYC document type

Revision ID: a1b2c3d4e5f6
Revises: 6f7a8b9c0d12
Create Date: 2026-06-22 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "6f7a8b9c0d12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ekyc_requests",
        sa.Column(
            "document_type",
            sa.String(length=20),
            nullable=False,
            server_default="CCCD",
        ),
    )


def downgrade() -> None:
    op.drop_column("ekyc_requests", "document_type")
