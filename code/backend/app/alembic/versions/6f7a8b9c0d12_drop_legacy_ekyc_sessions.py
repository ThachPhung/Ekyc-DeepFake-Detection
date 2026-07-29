"""Drop legacy eKYC sessions

Revision ID: 6f7a8b9c0d12
Revises: 5e6f7a8b9c01
Create Date: 2026-06-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "6f7a8b9c0d12"
down_revision = "5e6f7a8b9c01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("ekycsession"):
        op.drop_table("ekycsession")
    sa.Enum(name="ekycsessionstatus").drop(bind, checkfirst=True)


def downgrade() -> None:
    session_status = sa.Enum(
        "PENDING",
        "DOCUMENT_ANALYZED",
        "DOCUMENT_RETRY_REQUIRED",
        "READY_FOR_REVIEW",
        "APPROVED",
        "REJECTED",
        name="ekycsessionstatus",
    )
    session_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ekycsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=True),
        sa.Column("document_record_id", sa.String(length=255), nullable=True),
        sa.Column("document_analysis", sa.JSON(), nullable=True),
        sa.Column("review_reasons", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
