"""Add video eKYC step fields

Revision ID: 9b1c2d3e4f50
Revises: 8f2b7c6d9a01
Create Date: 2026-06-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "9b1c2d3e4f50"
down_revision = "8f2b7c6d9a01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ekyc_requests",
        sa.Column("video_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column(
            "video_status",
            sa.String(length=50),
            nullable=False,
            server_default="NOT_STARTED",
        ),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("video_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("face_similarity", sa.Float(), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("face_decision", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("video_error_message", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "ekyc_requests",
        sa.Column("video_processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_ekyc_requests_video_status"),
        "ekyc_requests",
        ["video_status"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_ekyc_requests_video_status"), table_name="ekyc_requests")
    op.drop_column("ekyc_requests", "video_processed_at")
    op.drop_column("ekyc_requests", "video_error_message")
    op.drop_column("ekyc_requests", "face_decision")
    op.drop_column("ekyc_requests", "face_similarity")
    op.drop_column("ekyc_requests", "video_result")
    op.drop_column("ekyc_requests", "video_status")
    op.drop_column("ekyc_requests", "video_path")
