"""Merge email verification and eKYC heads

Revision ID: d4e5f6a7b8c9
Revises: a3c9f2d4e5b6, c8d4e5f6a7b8
Create Date: 2026-06-24 17:45:00.000000

"""

from collections.abc import Sequence


revision: str = "d4e5f6a7b8c9"
down_revision: tuple[str, str] = ("a3c9f2d4e5b6", "c8d4e5f6a7b8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
