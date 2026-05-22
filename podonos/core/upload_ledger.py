from __future__ import annotations

import os
import hashlib
import json
import sqlite3
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence

from podonos.common.redaction import redact_secrets


LEDGER_STATUSES = {
    "queued",
    "md5_ready",
    "uploaded",
    "metadata_registering",
    "metadata_registered",
    "verified",
    "upload_failed",
    "verify_failed",
}


def build_upload_manifest_key(
    file_contract: Dict[str, Any], content_md5: str, file_size: int
) -> str:
    """Hash the stable local-file + evaluation metadata identity for resume."""

    stable_contract = dict(file_contract)
    stable_contract.pop("uploaded_file_name", None)
    payload = {
        "content_md5": content_md5,
        "file_size": file_size,
        "file_contract": stable_contract,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_upload_manifest_hash(
    file_contract: Dict[str, Any], content_md5: str, file_size: int
) -> str:
    """Hash the immutable local-file + metadata contract used for resume safety."""

    payload = {
        "content_md5": content_md5,
        "file_size": file_size,
        "file_contract": file_contract,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class UploadLedgerRow:
    evaluation_id: str
    remote_object_name: str
    local_path: str
    status: str
    created_at: str
    updated_at: str
    file_index: Optional[int] = None
    content_md5: Optional[str] = None
    file_size: Optional[int] = None
    manifest_key: Optional[str] = None
    manifest_hash: Optional[str] = None
    upload_start_at: Optional[str] = None
    upload_finish_at: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class InvalidUploadLedgerTransition(ValueError):
    """Raised when a ledger row is advanced through an invalid status transition."""


class UploadLedger:
    """SQLite upload progress ledger for one SDK process with multiple threads.

    Concurrency model:
    - This class is intentionally scoped to a single Python process. Multi-process
      writers are out of scope for the first opt-in resumability implementation.
    - Each operation opens a short-lived SQLite connection and owns one per-row
      transaction. A process-local RLock serializes writes made through the same
      UploadLedger instance, while SQLite's finite busy timeout protects callers
      from blocking indefinitely if another connection holds the database lock.
    - Ledger data is SDK-local progress state only; it is never backend truth.
    """

    def __init__(
        self,
        path: str,
        busy_timeout_ms: int = 1000,
    ) -> None:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be >= 1")

        self._requested_path = os.path.abspath(path)
        self.path = self._requested_path
        self.busy_timeout_ms = busy_timeout_ms
        self._lock = threading.RLock()
        self._initialize_schema()

    def upsert_queued_file(
        self,
        evaluation_id: str,
        remote_object_name: str,
        local_path: str,
        file_index: Optional[int] = None,
        manifest_key: Optional[str] = None,
    ) -> UploadLedgerRow:
        """Insert a queued row if missing; never downgrade an existing row."""

        self._validate_identity(evaluation_id, remote_object_name)
        if not isinstance(local_path, str) or not local_path:
            raise ValueError("local_path must be a non-empty string")
        local_path = os.path.abspath(local_path)
        if file_index is not None and (
            not isinstance(file_index, int) or file_index < 0
        ):
            raise ValueError("file_index must be a non-negative integer or None")
        if manifest_key is not None and (
            not isinstance(manifest_key, str) or not manifest_key
        ):
            raise ValueError("manifest_key must be a non-empty string or None")

        def _op(conn: sqlite3.Connection) -> UploadLedgerRow:
            existing = self._fetch_row(conn, evaluation_id, remote_object_name)
            if existing:
                return existing
            existing_by_index = (
                self._fetch_row_by_file_index(conn, evaluation_id, file_index)
                if file_index is not None
                else None
            )
            if manifest_key is not None:
                existing_by_manifest = self._fetch_rows_by_manifest_key(
                    conn, evaluation_id, manifest_key
                )
                if len(existing_by_manifest) == 1:
                    manifest_row = existing_by_manifest[0]
                    if file_index is None:
                        return manifest_row
                    if existing_by_index is not None:
                        if existing_by_index.manifest_key == manifest_key:
                            return existing_by_index
                        return manifest_row
                    # A single manifest match without a matching file index is
                    # ambiguous: it may be a deliberate duplicate occurrence in
                    # the same run. Prefer inserting a distinct row over
                    # under-uploading by collapsing two logical files.
                elif len(existing_by_manifest) > 1:
                    if existing_by_index is not None:
                        if existing_by_index.manifest_key in (None, manifest_key):
                            return existing_by_index
                        raise ValueError(
                            "Upload ledger file_index matches a different file "
                            "manifest; resume with the original files or start a "
                            "fresh evaluation."
                        )
                    if file_index is None:
                        raise ValueError(
                            "Upload ledger manifest identity is ambiguous; provide "
                            "a file_index or start a fresh evaluation."
                        )
            if existing_by_index:
                if (
                    manifest_key is not None
                    and existing_by_index.manifest_key is not None
                    and existing_by_index.manifest_key != manifest_key
                ):
                    raise ValueError(
                        "Upload ledger file_index matches a different file "
                        "manifest; resume with the original files or start a "
                        "fresh evaluation."
                    )
                return existing_by_index

            now = self._now()
            conn.execute(
                """
                INSERT INTO upload_ledger (
                    evaluation_id,
                    remote_object_name,
                    local_path,
                    file_index,
                    manifest_key,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    remote_object_name,
                    local_path,
                    file_index,
                    manifest_key,
                    "queued",
                    now,
                    now,
                ),
            )
            row = self._fetch_row(conn, evaluation_id, remote_object_name)
            assert row is not None
            return row

        return self._write_transaction(_op)

    def reset_for_reupload(
        self,
        evaluation_id: str,
        remote_object_name: str,
        local_path: str,
    ) -> UploadLedgerRow:
        """Reset a non-final row so the same remote object can be uploaded again."""

        if not isinstance(local_path, str) or not local_path:
            raise ValueError("local_path must be a non-empty string")
        local_path = os.path.abspath(local_path)
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="queued",
            allowed_from=tuple(LEDGER_STATUSES),
            updates={
                "local_path": local_path,
                "content_md5": None,
                "file_size": None,
                "manifest_key": None,
                "manifest_hash": None,
                "upload_start_at": None,
                "upload_finish_at": None,
                "error_type": None,
                "error_message": None,
            },
        )

    def mark_md5_ready(
        self,
        evaluation_id: str,
        remote_object_name: str,
        content_md5: str,
        file_size: int,
        manifest_hash: Optional[str] = None,
        manifest_key: Optional[str] = None,
    ) -> UploadLedgerRow:
        if not isinstance(content_md5, str) or not content_md5:
            raise ValueError("content_md5 must be a non-empty string")
        if not isinstance(file_size, int) or file_size < 1:
            raise ValueError("file_size must be a positive integer")
        if manifest_hash is not None and (
            not isinstance(manifest_hash, str) or not manifest_hash
        ):
            raise ValueError("manifest_hash must be a non-empty string or None")
        if manifest_key is not None and (
            not isinstance(manifest_key, str) or not manifest_key
        ):
            raise ValueError("manifest_key must be a non-empty string or None")
        updates: Dict[str, Any] = {"content_md5": content_md5, "file_size": file_size}
        if manifest_key is not None:
            updates["manifest_key"] = manifest_key
        if manifest_hash is not None:
            updates["manifest_hash"] = manifest_hash
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="md5_ready",
            allowed_from=("queued", "md5_ready", "upload_failed", "verify_failed"),
            updates=updates,
        )

    def mark_uploaded(
        self,
        evaluation_id: str,
        remote_object_name: str,
        upload_start_at: str,
        upload_finish_at: str,
    ) -> UploadLedgerRow:
        if not isinstance(upload_start_at, str) or not upload_start_at:
            raise ValueError("upload_start_at must be a non-empty string")
        if not isinstance(upload_finish_at, str) or not upload_finish_at:
            raise ValueError("upload_finish_at must be a non-empty string")
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="uploaded",
            allowed_from=("md5_ready", "uploaded"),
            updates={
                "upload_start_at": upload_start_at,
                "upload_finish_at": upload_finish_at,
                "error_type": None,
                "error_message": None,
            },
        )

    def mark_metadata_registered(
        self, evaluation_id: str, remote_object_name: str
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="metadata_registered",
            allowed_from=(
                "uploaded",
                "metadata_registering",
                "metadata_registered",
                "verify_failed",
            ),
            updates={"error_type": None, "error_message": None},
        )

    def mark_metadata_registering(
        self, evaluation_id: str, remote_object_name: str
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="metadata_registering",
            allowed_from=("uploaded", "metadata_registering"),
            updates={"error_type": None, "error_message": None},
        )

    def mark_metadata_registration_retry_needed(
        self,
        evaluation_id: str,
        remote_object_name: str,
        error_type: str,
        error_message: str,
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="uploaded",
            allowed_from=("metadata_registering",),
            updates={
                "error_type": redact_secrets(error_type),
                "error_message": redact_secrets(error_message),
            },
        )

    def mark_verified(
        self, evaluation_id: str, remote_object_name: str
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="verified",
            allowed_from=(
                "uploaded",
                "metadata_registering",
                "metadata_registered",
                "verify_failed",
                "verified",
            ),
            updates={"error_type": None, "error_message": None},
        )

    def mark_upload_failed(
        self,
        evaluation_id: str,
        remote_object_name: str,
        error_type: str,
        error_message: str,
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="upload_failed",
            allowed_from=tuple(LEDGER_STATUSES),
            updates={
                "error_type": redact_secrets(error_type),
                "error_message": redact_secrets(error_message),
            },
        )

    def mark_verify_failed(
        self,
        evaluation_id: str,
        remote_object_name: str,
        error_type: str,
        error_message: str,
    ) -> UploadLedgerRow:
        return self._transition(
            evaluation_id,
            remote_object_name,
            target_status="verify_failed",
            allowed_from=("uploaded", "metadata_registered", "verify_failed"),
            updates={
                "error_type": redact_secrets(error_type),
                "error_message": redact_secrets(error_message),
            },
        )

    def get(
        self, evaluation_id: str, remote_object_name: str
    ) -> Optional[UploadLedgerRow]:
        self._validate_identity(evaluation_id, remote_object_name)
        with self._connect() as conn:
            return self._fetch_row(conn, evaluation_id, remote_object_name)

    def list_by_status(
        self, evaluation_id: str, status: str
    ) -> List[UploadLedgerRow]:
        self._validate_status(status)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM upload_ledger
                WHERE evaluation_id = ? AND status = ?
                ORDER BY remote_object_name
                """,
                (evaluation_id, status),
            ).fetchall()
            return [self._row_from_sql(row) for row in rows]

    def counts_by_status(self, evaluation_id: str) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM upload_ledger
                WHERE evaluation_id = ?
                GROUP BY status
                """,
                (evaluation_id,),
            ).fetchall()
        counts = {status: 0 for status in LEDGER_STATUSES}
        counts.update({str(row["status"]): int(row["count"]) for row in rows})
        return counts

    def mark_processed(
        self,
        evaluation_id: str,
        processing_count: int = 0,
        request_hash: Optional[str] = None,
    ) -> None:
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        if not isinstance(processing_count, int) or processing_count < 0:
            raise ValueError("processing_count must be a non-negative integer")
        if request_hash is not None and (
            not isinstance(request_hash, str) or not request_hash
        ):
            raise ValueError("request_hash must be a non-empty string or None")

        def _op(conn: sqlite3.Connection) -> None:
            now = self._now()
            conn.execute(
                """
                INSERT INTO upload_ledger_finalization (
                    evaluation_id,
                    processed_at,
                    processing_count,
                    processed_request_hash,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                    processed_at = excluded.processed_at,
                    processing_count = excluded.processing_count,
                    processed_request_hash = excluded.processed_request_hash,
                    updated_at = excluded.updated_at
                """,
                (evaluation_id, now, processing_count, request_hash, now, now),
            )

        self._write_transaction(_op)

    def is_processed(
        self, evaluation_id: str, request_hash: Optional[str] = None
    ) -> bool:
        return self._finalization_column_matches(
            evaluation_id, "processed_at", "processed_request_hash", request_hash
        )

    def mark_session_json_uploaded(
        self, evaluation_id: str, session_json_hash: Optional[str] = None
    ) -> None:
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        if session_json_hash is not None and (
            not isinstance(session_json_hash, str) or not session_json_hash
        ):
            raise ValueError("session_json_hash must be a non-empty string or None")

        def _op(conn: sqlite3.Connection) -> None:
            now = self._now()
            conn.execute(
                """
                INSERT INTO upload_ledger_finalization (
                    evaluation_id,
                    session_json_uploaded_at,
                    session_json_hash,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                    session_json_uploaded_at = excluded.session_json_uploaded_at,
                    session_json_hash = excluded.session_json_hash,
                    updated_at = excluded.updated_at
                """,
                (evaluation_id, now, session_json_hash, now, now),
            )

        self._write_transaction(_op)

    def is_session_json_uploaded(
        self, evaluation_id: str, session_json_hash: Optional[str] = None
    ) -> bool:
        return self._finalization_column_matches(
            evaluation_id,
            "session_json_uploaded_at",
            "session_json_hash",
            session_json_hash,
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Private transaction helper used by ledger operations and atomicity tests."""

        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
            finally:
                conn.close()

    def _write_transaction(self, callback: Any) -> Any:
        with self._transaction() as conn:
            return callback(conn)

    def _transition(
        self,
        evaluation_id: str,
        remote_object_name: str,
        target_status: str,
        allowed_from: Sequence[str],
        updates: Dict[str, Any],
    ) -> UploadLedgerRow:
        self._validate_identity(evaluation_id, remote_object_name)
        self._validate_status(target_status)
        for status in allowed_from:
            self._validate_status(status)

        def _op(conn: sqlite3.Connection) -> UploadLedgerRow:
            row = self._fetch_row(conn, evaluation_id, remote_object_name)
            if row is None:
                raise KeyError(
                    f"No upload ledger row for {evaluation_id}/{remote_object_name}"
                )
            if row.status not in allowed_from:
                raise InvalidUploadLedgerTransition(
                    f"Cannot transition {remote_object_name} from {row.status} "
                    f"to {target_status}"
                )

            now = self._now()
            update_values = {**updates, "status": target_status, "updated_at": now}
            assignments = ", ".join(f"{column} = ?" for column in update_values)
            params: List[Any] = list(update_values.values())
            params.extend([evaluation_id, remote_object_name])
            conn.execute(
                f"""
                UPDATE upload_ledger
                SET {assignments}
                WHERE evaluation_id = ? AND remote_object_name = ?
                """,
                params,
            )
            updated = self._fetch_row(conn, evaluation_id, remote_object_name)
            assert updated is not None
            return updated

        return self._write_transaction(_op)

    def get_evaluation_contract(self, evaluation_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT contract_json
                FROM upload_ledger_contracts
                WHERE evaluation_id = ?
                """,
                (evaluation_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["contract_json"]))

    def set_evaluation_contract(
        self,
        evaluation_id: str,
        contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        if not isinstance(contract, dict) or not contract:
            raise ValueError("contract must be a non-empty dictionary")

        contract_json = json.dumps(contract, sort_keys=True, separators=(",", ":"))

        def _op(conn: sqlite3.Connection) -> Dict[str, Any]:
            now = self._now()
            conn.execute(
                """
                INSERT INTO upload_ledger_contracts (
                    evaluation_id,
                    contract_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                    contract_json = excluded.contract_json,
                    updated_at = excluded.updated_at
                """,
                (evaluation_id, contract_json, now, now),
            )
            return contract

        return self._write_transaction(_op)

    def _initialize_schema(self) -> None:
        self._ensure_safe_parent_directory()
        self._ensure_safe_file_path()
        old_umask: Optional[int] = None
        if os.name != "nt" and not os.path.exists(self.path):
            old_umask = os.umask(0o177)
        try:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS upload_ledger (
                        evaluation_id TEXT NOT NULL,
                        remote_object_name TEXT NOT NULL,
                        local_path TEXT NOT NULL,
                        file_index INTEGER,
                        status TEXT NOT NULL,
                        content_md5 TEXT,
                        file_size INTEGER,
                        manifest_key TEXT,
                        manifest_hash TEXT,
                        upload_start_at TEXT,
                        upload_finish_at TEXT,
                        error_type TEXT,
                        error_message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (evaluation_id, remote_object_name),
                        CHECK (status IN (
                            'queued',
                            'md5_ready',
                            'uploaded',
                            'metadata_registering',
                            'metadata_registered',
                            'verified',
                            'upload_failed',
                            'verify_failed'
                        ))
                    );
                    CREATE INDEX IF NOT EXISTS idx_upload_ledger_status
                        ON upload_ledger (evaluation_id, status);
                    CREATE TABLE IF NOT EXISTS upload_ledger_contracts (
                        evaluation_id TEXT PRIMARY KEY,
                        contract_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS upload_ledger_finalization (
                        evaluation_id TEXT PRIMARY KEY,
                        processed_at TEXT,
                        processing_count INTEGER,
                        processed_request_hash TEXT,
                        session_json_uploaded_at TEXT,
                        session_json_hash TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                self._ensure_column(conn, "file_index", "INTEGER")
                self._ensure_column(conn, "manifest_key", "TEXT")
                self._ensure_column(conn, "manifest_hash", "TEXT")
                self._ensure_table_column(
                    conn,
                    "upload_ledger_finalization",
                    "processed_request_hash",
                    "TEXT",
                )
                self._ensure_table_column(
                    conn,
                    "upload_ledger_finalization",
                    "session_json_hash",
                    "TEXT",
                )
                self._migrate_status_check_if_needed(conn)
                self._deduplicate_file_indexes(conn)
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_upload_ledger_status
                        ON upload_ledger (evaluation_id, status)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_upload_ledger_file_index
                        ON upload_ledger (evaluation_id, file_index)
                    """
                )
                conn.execute(
                    """
                    DROP INDEX IF EXISTS ux_upload_ledger_evaluation_file_index
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_upload_ledger_manifest_key
                        ON upload_ledger (evaluation_id, manifest_key)
                    """
                )
        finally:
            if old_umask is not None:
                os.umask(old_umask)
        self._harden_permissions()

    def _ensure_safe_parent_directory(self) -> None:
        parent = os.path.dirname(self._requested_path)
        if not parent:
            return
        if os.name == "nt":
            os.makedirs(parent, exist_ok=True)
            return

        root = os.path.abspath(os.sep)
        rel_parent = os.path.relpath(parent, root)
        rel_parts = [] if rel_parent == "." else rel_parent.split(os.sep)
        dir_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            dir_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            dir_flags |= os.O_NOFOLLOW

        dir_fds: List[int] = []
        try:
            current_path = root
            current_fd = os.open(root, dir_flags)
            dir_fds.append(current_fd)
            for part in rel_parts:
                if part in {"", ".", ".."}:
                    raise ValueError("upload_state_path parent is invalid")
                candidate_path = os.path.join(current_path, part)
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                try:
                    next_fd = os.open(part, dir_flags, dir_fd=current_fd)
                    current_path = candidate_path
                except OSError:
                    if not self._is_allowed_platform_symlink(candidate_path):
                        raise
                    resolved_candidate = os.path.realpath(candidate_path)
                    next_fd = os.open(resolved_candidate, dir_flags)
                    current_path = resolved_candidate
                current_fd = next_fd
                dir_fds.append(current_fd)
        except OSError as exc:
            raise ValueError(
                "upload_state_path parent must not contain symlinks"
            ) from exc
        finally:
            for fd in reversed(dir_fds):
                try:
                    os.close(fd)
                except OSError:
                    pass

    @staticmethod
    def _is_allowed_platform_symlink(path: str) -> bool:
        """Allow macOS system temp aliases while rejecting caller-created links."""

        allowed_aliases = {
            "/var": "/private/var",
            "/tmp": "/private/tmp",
        }
        expected_target = allowed_aliases.get(path)
        if expected_target is None:
            return False
        return os.path.islink(path) and os.path.realpath(path) == expected_target

    def _ensure_safe_file_path(self) -> None:
        if os.name == "nt":
            return
        try:
            requested_stat = os.lstat(self._requested_path)
            if stat.S_ISLNK(requested_stat.st_mode):
                raise ValueError("upload_state_path must not be a symlink")
            path_stat = os.lstat(self._requested_path)
        except FileNotFoundError:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(self._requested_path, flags, 0o600)
            except FileExistsError:
                self._ensure_safe_file_path()
                return
            except OSError as exc:
                raise ValueError(
                    "upload_state_path must not be a symlink or unsafe file path"
                ) from exc
            else:
                os.close(fd)
            return

        if stat.S_ISLNK(path_stat.st_mode):
            raise ValueError("upload_state_path must not be a symlink")
        if not stat.S_ISREG(path_stat.st_mode):
            raise ValueError("upload_state_path must be a regular file")

    def _ensure_column(
        self, conn: sqlite3.Connection, column_name: str, column_type: str
    ) -> None:
        self._ensure_table_column(conn, "upload_ledger", column_name, column_type)

    def _ensure_table_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        if not table_name.replace("_", "").isalnum():
            raise ValueError("table_name must contain only alphanumeric characters and underscores")
        if not column_name.replace("_", "").isalnum():
            raise ValueError("column_name must contain only alphanumeric characters and underscores")
        existing_columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )

    def _migrate_status_check_if_needed(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'upload_ledger'
            """
        ).fetchone()
        if row is None or "metadata_registering" in str(row["sql"]):
            return

        conn.executescript(
            """
            ALTER TABLE upload_ledger RENAME TO upload_ledger_old;
            CREATE TABLE upload_ledger (
                evaluation_id TEXT NOT NULL,
                remote_object_name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                file_index INTEGER,
                status TEXT NOT NULL,
                content_md5 TEXT,
                file_size INTEGER,
                manifest_key TEXT,
                manifest_hash TEXT,
                upload_start_at TEXT,
                upload_finish_at TEXT,
                error_type TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (evaluation_id, remote_object_name),
                CHECK (status IN (
                    'queued',
                    'md5_ready',
                    'uploaded',
                    'metadata_registering',
                    'metadata_registered',
                    'verified',
                    'upload_failed',
                    'verify_failed'
                ))
            );
            INSERT INTO upload_ledger (
                evaluation_id,
                remote_object_name,
                local_path,
                file_index,
                status,
                content_md5,
                file_size,
                manifest_key,
                manifest_hash,
                upload_start_at,
                upload_finish_at,
                error_type,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                evaluation_id,
                remote_object_name,
                local_path,
                file_index,
                status,
                content_md5,
                file_size,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM pragma_table_info('upload_ledger_old')
                        WHERE name = 'manifest_key'
                    )
                    THEN manifest_key
                    ELSE NULL
                END,
                manifest_hash,
                upload_start_at,
                upload_finish_at,
                error_type,
                error_message,
                created_at,
                updated_at
            FROM upload_ledger_old;
            DROP TABLE upload_ledger_old;
            """
        )

    def _deduplicate_file_indexes(self, conn: sqlite3.Connection) -> None:
        # File order is no longer identity. Keep legacy duplicate indexes as
        # diagnostics instead of mutating them for a uniqueness constraint.
        return

    def _harden_permissions(self) -> None:
        if os.name == "nt" or not os.path.exists(self.path):
            return
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _fetch_row(
        self, conn: sqlite3.Connection, evaluation_id: str, remote_object_name: str
    ) -> Optional[UploadLedgerRow]:
        row = conn.execute(
            """
            SELECT * FROM upload_ledger
            WHERE evaluation_id = ? AND remote_object_name = ?
            """,
            (evaluation_id, remote_object_name),
        ).fetchone()
        if row is None:
            return None
        return self._row_from_sql(row)

    def _row_from_sql(self, row: sqlite3.Row) -> UploadLedgerRow:
        return UploadLedgerRow(
            evaluation_id=str(row["evaluation_id"]),
            remote_object_name=str(row["remote_object_name"]),
            local_path=str(row["local_path"]),
            status=str(row["status"]),
            file_index=row["file_index"],
            content_md5=row["content_md5"],
            file_size=row["file_size"],
            manifest_key=row["manifest_key"],
            manifest_hash=row["manifest_hash"],
            upload_start_at=row["upload_start_at"],
            upload_finish_at=row["upload_finish_at"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _fetch_row_by_file_index(
        self, conn: sqlite3.Connection, evaluation_id: str, file_index: int
    ) -> Optional[UploadLedgerRow]:
        row = conn.execute(
            """
            SELECT * FROM upload_ledger
            WHERE evaluation_id = ? AND file_index = ?
            ORDER BY created_at
            LIMIT 1
            """,
            (evaluation_id, file_index),
        ).fetchone()
        if row is None:
            return None
        return self._row_from_sql(row)

    def _fetch_rows_by_manifest_key(
        self, conn: sqlite3.Connection, evaluation_id: str, manifest_key: str
    ) -> List[UploadLedgerRow]:
        rows = conn.execute(
            """
            SELECT *
            FROM upload_ledger
            WHERE evaluation_id = ? AND manifest_key = ?
            ORDER BY file_index ASC, remote_object_name ASC
            """,
            (evaluation_id, manifest_key),
        ).fetchall()
        return [self._row_from_sql(row) for row in rows]

    def _finalization_column_matches(
        self,
        evaluation_id: str,
        timestamp_column: str,
        hash_column: str,
        expected_hash: Optional[str],
    ) -> bool:
        if timestamp_column not in {"processed_at", "session_json_uploaded_at"}:
            raise ValueError("unsupported finalization column")
        if hash_column not in {"processed_request_hash", "session_json_hash"}:
            raise ValueError("unsupported finalization hash column")
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        if expected_hash is not None and (
            not isinstance(expected_hash, str) or not expected_hash
        ):
            raise ValueError("expected_hash must be a non-empty string or None")
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT {timestamp_column}, {hash_column}
                FROM upload_ledger_finalization
                WHERE evaluation_id = ?
                """,
                (evaluation_id,),
            ).fetchone()
        if row is None or row[timestamp_column] is None:
            return False
        if expected_hash is None:
            return True
        return row[hash_column] == expected_hash

    def _validate_identity(self, evaluation_id: str, remote_object_name: str) -> None:
        if not isinstance(evaluation_id, str) or not evaluation_id:
            raise ValueError("evaluation_id must be a non-empty string")
        if not isinstance(remote_object_name, str) or not remote_object_name:
            raise ValueError("remote_object_name must be a non-empty string")

    def _validate_status(self, status: str) -> None:
        if status not in LEDGER_STATUSES:
            raise ValueError(f"Unknown upload ledger status: {status}")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
