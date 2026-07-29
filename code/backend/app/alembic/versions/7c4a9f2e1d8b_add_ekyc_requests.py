"""Add ekyc requests

Revision ID: 7c4a9f2e1d8b
Revises: 7b7a3c4f8d2e
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "7c4a9f2e1d8b"
down_revision = "7b7a3c4f8d2e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ekyc_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=13), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.Column("ocr_result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_requests_request_id"),
        "ekyc_requests",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_ekyc_requests_status"),
        "ekyc_requests",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_ekyc_requests_status"), table_name="ekyc_requests")
    op.drop_index(op.f("ix_ekyc_requests_request_id"), table_name="ekyc_requests")
    op.drop_table("ekyc_requests")
