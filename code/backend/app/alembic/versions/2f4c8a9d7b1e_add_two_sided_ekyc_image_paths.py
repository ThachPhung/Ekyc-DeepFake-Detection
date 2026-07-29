"""Add two-sided eKYC image paths

Revision ID: 2f4c8a9d7b1e
Revises: 7c4a9f2e1d8b
Create Date: 2026-06-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "2f4c8a9d7b1e"
down_revision = "7c4a9f2e1d8b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ekyc_requests",
        sa.Column("front_image_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("back_image_path", sa.String(length=1024), nullable=True),
    )
    op.execute("UPDATE ekyc_requests SET front_image_path = image_path")


def downgrade():
    op.drop_column("ekyc_requests", "back_image_path")
    op.drop_column("ekyc_requests", "front_image_path")
