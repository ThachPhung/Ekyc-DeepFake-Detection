"""Add admin audit logs

Revision ID: audit20260701
Revises: f1a2b3c4d5e6
Create Date: 2026-07-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "audit20260701"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("target_label", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_audit_logs_action"),
        "admin_audit_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_audit_logs_actor_email"),
        "admin_audit_logs",
        ["actor_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_audit_logs_actor_user_id"),
        "admin_audit_logs",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_audit_logs_created_at"),
        "admin_audit_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_audit_logs_target_id"),
        "admin_audit_logs",
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_audit_logs_target_type"),
        "admin_audit_logs",
        ["target_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_logs_target_type"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_target_id"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_created_at"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_actor_user_id"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_actor_email"), table_name="admin_audit_logs")
    op.drop_index(op.f("ix_admin_audit_logs_action"), table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
