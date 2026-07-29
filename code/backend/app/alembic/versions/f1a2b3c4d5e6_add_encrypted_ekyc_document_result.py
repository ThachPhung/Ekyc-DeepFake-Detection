"""Add encrypted eKYC document result

Revision ID: f1a2b3c4d5e6
Revises: e9f1a2b3c4d5
Create Date: 2026-06-30 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e9f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ekyc_results",
        sa.Column("encrypted_document_result", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ekyc_results", "encrypted_document_result")
