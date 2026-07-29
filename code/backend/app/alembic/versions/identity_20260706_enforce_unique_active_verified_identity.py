"""Enforce unique active verified identities by identity number

Revision ID: identity20260706
Revises: voice20260704
Create Date: 2026-07-06 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "identity20260706"
down_revision = "voice20260704"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _has_active_duplicates() -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT identity_number_hash
            FROM verified_identities
            WHERE revoked_at IS NULL
            GROUP BY identity_number_hash
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    return result is not None


def upgrade() -> None:
    if _has_active_duplicates():
        raise RuntimeError(
            "Cannot enforce unique active identity numbers because duplicate active "
            "verified identities already exist. Revoke or clean up duplicates first."
        )

    _drop_index_if_exists(
        "ix_verified_identities_identity_number_hash",
        "verified_identities",
    )
    op.create_index(
        "ux_verified_identities_active_identity_number_hash",
        "verified_identities",
        ["identity_number_hash"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    _drop_index_if_exists(
        "ux_verified_identities_active_identity_number_hash",
        "verified_identities",
    )
    op.create_index(
        op.f("ix_verified_identities_identity_number_hash"),
        "verified_identities",
        ["identity_number_hash"],
        unique=False,
    )
