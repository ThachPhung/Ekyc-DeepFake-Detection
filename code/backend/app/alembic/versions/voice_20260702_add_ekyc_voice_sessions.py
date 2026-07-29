"""Add realtime eKYC voice sessions

Revision ID: voice20260702
Revises: settings20260701
Create Date: 2026-07-02 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "voice20260702"
down_revision = "settings20260701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ekyc_voice_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("display_digits", sa.JSON(), nullable=False),
        sa.Column("display_text", sa.String(length=50), nullable=False),
        sa.Column("expected_text", sa.String(length=255), nullable=False),
        sa.Column("spoken_hint", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("liveness_video_hash", sa.String(length=128), nullable=True),
        sa.Column("ai_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_voice_sessions_created_at"),
        "ekyc_voice_sessions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_sessions_status"),
        "ekyc_voice_sessions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_sessions_user_id"),
        "ekyc_voice_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ekyc_voice_sessions_user_id"), table_name="ekyc_voice_sessions")
    op.drop_index(op.f("ix_ekyc_voice_sessions_status"), table_name="ekyc_voice_sessions")
    op.drop_index(op.f("ix_ekyc_voice_sessions_created_at"), table_name="ekyc_voice_sessions")
    op.drop_table("ekyc_voice_sessions")
