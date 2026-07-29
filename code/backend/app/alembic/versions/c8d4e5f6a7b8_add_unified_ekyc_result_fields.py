"""Add unified eKYC result fields

Revision ID: c8d4e5f6a7b8
Revises: b7c2d9e4f6a1
Create Date: 2026-06-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c8d4e5f6a7b8"
down_revision = "b7c2d9e4f6a1"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    _drop_index_if_exists(op.f("ix_ekyc_video_results_status"), "ekyc_video_results")
    _drop_index_if_exists(
        op.f("ix_ekyc_video_results_session_id"),
        "ekyc_video_results",
    )
    _drop_table_if_exists("ekyc_video_results")
    _drop_index_if_exists(
        op.f("ix_ekyc_identity_confirmations_session_id"),
        "ekyc_identity_confirmations",
    )
    _drop_table_if_exists("ekyc_identity_confirmations")
    _drop_index_if_exists(op.f("ix_ekyc_ocr_results_status"), "ekyc_ocr_results")
    _drop_index_if_exists(
        op.f("ix_ekyc_ocr_results_session_id"),
        "ekyc_ocr_results",
    )
    _drop_table_if_exists("ekyc_ocr_results")
    _drop_index_if_exists(
        op.f("ix_ekyc_document_files_side"),
        "ekyc_document_files",
    )
    _drop_index_if_exists(
        op.f("ix_ekyc_document_files_session_id"),
        "ekyc_document_files",
    )
    op.rename_table("ekyc_document_files", "ekyc_files")
    op.alter_column("ekyc_files", "side", new_column_name="file_type")
    op.execute(
        """
        UPDATE ekyc_files
        SET file_type = CASE file_type
            WHEN 'FRONT' THEN 'DOCUMENT_FRONT'
            WHEN 'BACK' THEN 'DOCUMENT_BACK'
            ELSE file_type
        END
        """
    )
    op.create_index(
        op.f("ix_ekyc_files_file_type"),
        "ekyc_files",
        ["file_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_files_session_id"),
        "ekyc_files",
        ["session_id"],
        unique=False,
    )
    op.add_column("ekyc_sessions", sa.Column("result", sa.JSON(), nullable=True))
    op.add_column("ekyc_sessions", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("ekyc_sessions", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "ekyc_sessions",
        sa.Column("decision", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "ekyc_sessions",
        sa.Column("error_message", sa.String(length=1024), nullable=True),
    )
    op.create_table(
        "ekyc_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("document_result", sa.JSON(), nullable=True),
        sa.Column("liveness_result", sa.JSON(), nullable=True),
        sa.Column("voice_result", sa.JSON(), nullable=True),
        sa.Column("raw_result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["ekyc_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_ekyc_results_session_id"),
    )
    op.create_index(
        op.f("ix_ekyc_results_decision"),
        "ekyc_results",
        ["decision"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_results_session_id"),
        "ekyc_results",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_results_status"),
        "ekyc_results",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_results_user_id"),
        "ekyc_results",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "verified_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ekyc_result_id", sa.Uuid(), nullable=True),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("identity_number_hash", sa.String(length=128), nullable=False),
        sa.Column("identity_number_encrypted", sa.String(length=2048), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("birth_date", sa.String(length=50), nullable=True),
        sa.Column("gender", sa.String(length=50), nullable=True),
        sa.Column("nationality", sa.String(length=100), nullable=True),
        sa.Column("issued_date", sa.String(length=50), nullable=True),
        sa.Column("expired_date", sa.String(length=50), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ekyc_result_id"], ["ekyc_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ekyc_result_id", name="uq_verified_identities_ekyc_result_id"),
    )
    op.create_index(
        op.f("ix_verified_identities_ekyc_result_id"),
        "verified_identities",
        ["ekyc_result_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_verified_identities_identity_number_hash"),
        "verified_identities",
        ["identity_number_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verified_identities_user_id"),
        "verified_identities",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_verified_identities_user_id"), table_name="verified_identities")
    op.drop_index(
        op.f("ix_verified_identities_identity_number_hash"),
        table_name="verified_identities",
    )
    op.drop_index(
        op.f("ix_verified_identities_ekyc_result_id"),
        table_name="verified_identities",
    )
    op.drop_table("verified_identities")
    op.drop_index(op.f("ix_ekyc_results_user_id"), table_name="ekyc_results")
    op.drop_index(op.f("ix_ekyc_results_status"), table_name="ekyc_results")
    op.drop_index(op.f("ix_ekyc_results_session_id"), table_name="ekyc_results")
    op.drop_index(op.f("ix_ekyc_results_decision"), table_name="ekyc_results")
    op.drop_table("ekyc_results")
    op.drop_column("ekyc_sessions", "error_message")
    op.drop_column("ekyc_sessions", "decision")
    op.drop_column("ekyc_sessions", "confidence")
    op.drop_column("ekyc_sessions", "score")
    op.drop_column("ekyc_sessions", "result")
    op.drop_index(op.f("ix_ekyc_files_session_id"), table_name="ekyc_files")
    op.drop_index(op.f("ix_ekyc_files_file_type"), table_name="ekyc_files")
    op.execute(
        """
        UPDATE ekyc_files
        SET file_type = CASE file_type
            WHEN 'DOCUMENT_FRONT' THEN 'FRONT'
            WHEN 'DOCUMENT_BACK' THEN 'BACK'
            ELSE file_type
        END
        """
    )
    op.alter_column("ekyc_files", "file_type", new_column_name="side")
    op.rename_table("ekyc_files", "ekyc_document_files")
    op.create_index(
        op.f("ix_ekyc_document_files_side"),
        "ekyc_document_files",
        ["side"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_document_files_session_id"),
        "ekyc_document_files",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "ekyc_ocr_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("ocr_result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["ekyc_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_ocr_results_session_id"),
        "ekyc_ocr_results",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_ocr_results_status"),
        "ekyc_ocr_results",
        ["status"],
        unique=False,
    )
    op.create_table(
        "ekyc_identity_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_fields", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["ekyc_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_identity_confirmations_session_id"),
        "ekyc_identity_confirmations",
        ["session_id"],
        unique=False,
    )
    op.create_table(
        "ekyc_video_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("video_path", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("video_result", sa.JSON(), nullable=True),
        sa.Column("face_similarity", sa.Float(), nullable=True),
        sa.Column("face_decision", sa.String(length=50), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["ekyc_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_video_results_session_id"),
        "ekyc_video_results",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_video_results_status"),
        "ekyc_video_results",
        ["status"],
        unique=False,
    )
