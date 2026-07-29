"""Remodel eKYC requests into MVP tables

Revision ID: b7c2d9e4f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-23 00:00:00.000000

"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "b7c2d9e4f6a1"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _json_text(sql: str, *names: str) -> sa.TextClause:
    statement = sa.text(sql)
    return statement.bindparams(
        *(sa.bindparam(name, type_=sa.JSON()) for name in names)
    )


def _create_new_tables() -> None:
    op.create_table(
        "ekyc_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_sessions_request_id"),
        "ekyc_sessions",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_ekyc_sessions_status"),
        "ekyc_sessions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "ekyc_document_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["ekyc_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_document_files_session_id"),
        "ekyc_document_files",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_document_files_side"),
        "ekyc_document_files",
        ["side"],
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


def _drop_new_tables() -> None:
    op.drop_index(op.f("ix_ekyc_video_results_status"), table_name="ekyc_video_results")
    op.drop_index(
        op.f("ix_ekyc_video_results_session_id"),
        table_name="ekyc_video_results",
    )
    op.drop_table("ekyc_video_results")
    op.drop_index(
        op.f("ix_ekyc_identity_confirmations_session_id"),
        table_name="ekyc_identity_confirmations",
    )
    op.drop_table("ekyc_identity_confirmations")
    op.drop_index(op.f("ix_ekyc_ocr_results_status"), table_name="ekyc_ocr_results")
    op.drop_index(
        op.f("ix_ekyc_ocr_results_session_id"),
        table_name="ekyc_ocr_results",
    )
    op.drop_table("ekyc_ocr_results")
    op.drop_index(op.f("ix_ekyc_document_files_side"), table_name="ekyc_document_files")
    op.drop_index(
        op.f("ix_ekyc_document_files_session_id"),
        table_name="ekyc_document_files",
    )
    op.drop_table("ekyc_document_files")
    op.drop_index(op.f("ix_ekyc_sessions_status"), table_name="ekyc_sessions")
    op.drop_index(op.f("ix_ekyc_sessions_request_id"), table_name="ekyc_sessions")
    op.drop_table("ekyc_sessions")


def _create_legacy_table() -> None:
    op.create_table(
        "ekyc_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.Column("front_image_path", sa.String(length=1024), nullable=True),
        sa.Column("back_image_path", sa.String(length=1024), nullable=True),
        sa.Column("video_path", sa.String(length=1024), nullable=True),
        sa.Column("video_status", sa.String(length=50), nullable=False),
        sa.Column("ocr_result", sa.JSON(), nullable=True),
        sa.Column("video_result", sa.JSON(), nullable=True),
        sa.Column("document_confirmed_fields", sa.JSON(), nullable=True),
        sa.Column("document_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("face_similarity", sa.Float(), nullable=True),
        sa.Column("face_decision", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("video_error_message", sa.String(length=1024), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("video_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ekyc_requests_request_id"),
        "ekyc_requests",
        ["request_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_ekyc_requests_status"),
        "ekyc_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ekyc_requests_video_status"),
        "ekyc_requests",
        ["video_status"],
        unique=False,
    )


def _drop_legacy_table() -> None:
    op.drop_index(op.f("ix_ekyc_requests_video_status"), table_name="ekyc_requests")
    op.drop_index(op.f("ix_ekyc_requests_status"), table_name="ekyc_requests")
    op.drop_index(op.f("ix_ekyc_requests_request_id"), table_name="ekyc_requests")
    op.drop_table("ekyc_requests")


def upgrade() -> None:
    bind = op.get_bind()
    legacy_rows = bind.execute(sa.text("SELECT * FROM ekyc_requests")).mappings().all()
    _create_new_tables()

    for row in legacy_rows:
        session_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO ekyc_sessions (
                    id, request_id, user_id, status, document_type, model_version,
                    created_at, updated_at, processed_at
                )
                VALUES (
                    :id, :request_id, :user_id, :status, :document_type,
                    :model_version, :created_at, :updated_at, :processed_at
                )
                """
            ),
            {
                "id": session_id,
                "request_id": row["request_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "document_type": row["document_type"],
                "model_version": row["model_version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "processed_at": row["processed_at"],
            },
        )

        front_path = row["front_image_path"] or row["image_path"]
        if front_path:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO ekyc_document_files (
                        id, session_id, side, file_path, created_at
                    )
                    VALUES (:id, :session_id, 'FRONT', :file_path, :created_at)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "session_id": session_id,
                    "file_path": front_path,
                    "created_at": row["created_at"],
                },
            )
        if row["back_image_path"]:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO ekyc_document_files (
                        id, session_id, side, file_path, created_at
                    )
                    VALUES (:id, :session_id, 'BACK', :file_path, :created_at)
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "session_id": session_id,
                    "file_path": row["back_image_path"],
                    "created_at": row["created_at"],
                },
            )

        bind.execute(
            _json_text(
                """
                INSERT INTO ekyc_ocr_results (
                    id, session_id, status, ocr_result, error_message,
                    model_version, created_at, started_at, completed_at
                )
                VALUES (
                    :id, :session_id, :status, :ocr_result, :error_message,
                    :model_version, :created_at, :started_at, :completed_at
                )
                """
                ,
                "ocr_result",
            ),
            {
                "id": uuid.uuid4(),
                "session_id": session_id,
                "status": row["status"],
                "ocr_result": row["ocr_result"],
                "error_message": row["error_message"],
                "model_version": row["model_version"],
                "created_at": row["created_at"],
                "started_at": row["created_at"],
                "completed_at": row["processed_at"],
            },
        )

        if row["document_confirmed_fields"] is not None:
            bind.execute(
                _json_text(
                    """
                    INSERT INTO ekyc_identity_confirmations (
                        id, session_id, confirmed_fields, confirmed_at,
                        created_by_user_id
                    )
                    VALUES (
                        :id, :session_id, :confirmed_fields, :confirmed_at,
                        :created_by_user_id
                    )
                    """
                    ,
                    "confirmed_fields",
                ),
                {
                    "id": uuid.uuid4(),
                    "session_id": session_id,
                    "confirmed_fields": row["document_confirmed_fields"],
                    "confirmed_at": row["document_confirmed_at"] or row["updated_at"],
                    "created_by_user_id": row["user_id"],
                },
            )

        if (
            row["video_path"]
            or row["video_result"] is not None
            or row["video_status"] != "NOT_STARTED"
        ):
            bind.execute(
                _json_text(
                    """
                    INSERT INTO ekyc_video_results (
                        id, session_id, video_path, status, video_result,
                        face_similarity, face_decision, model_version,
                        error_message, created_at, started_at, completed_at
                    )
                    VALUES (
                        :id, :session_id, :video_path, :status, :video_result,
                        :face_similarity, :face_decision, :model_version,
                        :error_message, :created_at, :started_at, :completed_at
                    )
                    """
                    ,
                    "video_result",
                ),
                {
                    "id": uuid.uuid4(),
                    "session_id": session_id,
                    "video_path": row["video_path"],
                    "status": row["video_status"],
                    "video_result": row["video_result"],
                    "face_similarity": row["face_similarity"],
                    "face_decision": row["face_decision"],
                    "model_version": row["model_version"],
                    "error_message": row["video_error_message"],
                    "created_at": row["created_at"],
                    "started_at": row["created_at"],
                    "completed_at": row["video_processed_at"],
                },
            )

    _drop_legacy_table()


def downgrade() -> None:
    bind = op.get_bind()
    session_rows = bind.execute(sa.text("SELECT * FROM ekyc_sessions")).mappings().all()
    _create_legacy_table()

    for row in session_rows:
        front = bind.execute(
            sa.text(
                """
                SELECT file_path
                FROM ekyc_document_files
                WHERE session_id = :session_id AND side = 'FRONT'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"session_id": row["id"]},
        ).scalar()
        back = bind.execute(
            sa.text(
                """
                SELECT file_path
                FROM ekyc_document_files
                WHERE session_id = :session_id AND side = 'BACK'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"session_id": row["id"]},
        ).scalar()
        ocr = bind.execute(
            sa.text(
                """
                SELECT *
                FROM ekyc_ocr_results
                WHERE session_id = :session_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"session_id": row["id"]},
        ).mappings().first()
        confirmation = bind.execute(
            sa.text(
                """
                SELECT *
                FROM ekyc_identity_confirmations
                WHERE session_id = :session_id
                ORDER BY confirmed_at DESC
                LIMIT 1
                """
            ),
            {"session_id": row["id"]},
        ).mappings().first()
        video = bind.execute(
            sa.text(
                """
                SELECT *
                FROM ekyc_video_results
                WHERE session_id = :session_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"session_id": row["id"]},
        ).mappings().first()

        bind.execute(
            _json_text(
                """
                INSERT INTO ekyc_requests (
                    id, request_id, user_id, status, document_type, image_path,
                    front_image_path, back_image_path, video_path, video_status,
                    ocr_result, video_result, document_confirmed_fields,
                    document_confirmed_at, face_similarity, face_decision,
                    error_message, video_error_message, model_version,
                    created_at, updated_at, processed_at, video_processed_at
                )
                VALUES (
                    :id, :request_id, :user_id, :status, :document_type, :image_path,
                    :front_image_path, :back_image_path, :video_path, :video_status,
                    :ocr_result, :video_result, :document_confirmed_fields,
                    :document_confirmed_at, :face_similarity, :face_decision,
                    :error_message, :video_error_message, :model_version,
                    :created_at, :updated_at, :processed_at, :video_processed_at
                )
                """
                ,
                "ocr_result",
                "video_result",
                "document_confirmed_fields",
            ),
            {
                "id": row["id"],
                "request_id": row["request_id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "document_type": row["document_type"],
                "image_path": front or "",
                "front_image_path": front,
                "back_image_path": back,
                "video_path": video["video_path"] if video else None,
                "video_status": video["status"] if video else "NOT_STARTED",
                "ocr_result": ocr["ocr_result"] if ocr else None,
                "video_result": video["video_result"] if video else None,
                "document_confirmed_fields": (
                    confirmation["confirmed_fields"] if confirmation else None
                ),
                "document_confirmed_at": (
                    confirmation["confirmed_at"] if confirmation else None
                ),
                "face_similarity": video["face_similarity"] if video else None,
                "face_decision": video["face_decision"] if video else None,
                "error_message": ocr["error_message"] if ocr else None,
                "video_error_message": video["error_message"] if video else None,
                "model_version": row["model_version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "processed_at": row["processed_at"],
                "video_processed_at": video["completed_at"] if video else None,
            },
        )

    _drop_new_tables()
