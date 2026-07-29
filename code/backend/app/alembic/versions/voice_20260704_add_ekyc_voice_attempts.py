"""Add eKYC voice attempt records

Revision ID: voice20260704
Revises: voice20260702
Create Date: 2026-07-04 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "voice20260704"
down_revision = "voice20260702"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ekyc_voice_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("voice_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("challenge_display_text", sa.String(length=50), nullable=False),
        sa.Column("challenge_expected_text", sa.String(length=255), nullable=False),
        sa.Column("challenge_spoken_hint", sa.String(length=255), nullable=False),
        sa.Column("ai_result", sa.JSON(), nullable=True),
        sa.Column("liveness_video_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["voice_session_id"],
            ["ekyc_voice_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_attempt_number"),
        "ekyc_voice_attempts",
        ["attempt_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_created_at"),
        "ekyc_voice_attempts",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_decision"),
        "ekyc_voice_attempts",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_status"),
        "ekyc_voice_attempts",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_user_id"),
        "ekyc_voice_attempts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_voice_attempts_voice_session_id"),
        "ekyc_voice_attempts",
        ["voice_session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ekyc_voice_attempts_voice_session_id"),
        table_name="ekyc_voice_attempts",
    )
    op.drop_index(op.f("ix_ekyc_voice_attempts_user_id"), table_name="ekyc_voice_attempts")
    op.drop_index(op.f("ix_ekyc_voice_attempts_status"), table_name="ekyc_voice_attempts")
    op.drop_index(op.f("ix_ekyc_voice_attempts_decision"), table_name="ekyc_voice_attempts")
    op.drop_index(op.f("ix_ekyc_voice_attempts_created_at"), table_name="ekyc_voice_attempts")
    op.drop_index(
        op.f("ix_ekyc_voice_attempts_attempt_number"),
        table_name="ekyc_voice_attempts",
    )
    op.drop_table("ekyc_voice_attempts")
