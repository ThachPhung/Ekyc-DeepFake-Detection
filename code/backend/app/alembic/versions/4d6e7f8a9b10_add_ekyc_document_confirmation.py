"""Add eKYC document confirmation fields

Revision ID: 4d6e7f8a9b10
Revises: 9b1c2d3e4f50
Create Date: 2026-06-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "4d6e7f8a9b10"
down_revision = "9b1c2d3e4f50"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ekyc_requests",
        sa.Column("document_confirmed_fields", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("document_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("ekyc_requests", "document_confirmed_at")
    op.drop_column("ekyc_requests", "document_confirmed_fields")
