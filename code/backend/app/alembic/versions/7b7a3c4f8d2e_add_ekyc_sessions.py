"""Add ekyc sessions

Revision ID: 7b7a3c4f8d2e
Revises: fe56fa70289e
Create Date: 2026-06-18 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7b7a3c4f8d2e"
down_revision: str | None = "fe56fa70289e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ekycsession",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "DOCUMENT_ANALYZED",
                "DOCUMENT_RETRY_REQUIRED",
                "READY_FOR_REVIEW",
                "APPROVED",
                "REJECTED",
                name="ekycsessionstatus",
            ),
            nullable=False,
        ),
        sa.Column("document_type", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column("document_record_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("document_analysis", sa.JSON(), nullable=True),
        sa.Column("review_reasons", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ekycsession")
    sa.Enum(name="ekycsessionstatus").drop(op.get_bind(), checkfirst=True)
