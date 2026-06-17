import os
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from podonos.core.upload_ledger import (
    InvalidUploadLedgerTransition,
    UploadLedger,
    build_upload_manifest_key,
    stable_manifest_contract,
)


class TestUploadLedger(unittest.TestCase):
    def make_ledger(self, busy_timeout_ms: int = 1000):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = os.path.join(temp_dir.name, "upload-state.sqlite")
        return UploadLedger(path, busy_timeout_ms=busy_timeout_ms), path

    def test_idempotent_status_transitions_counts_and_listing(self):
        ledger, _ = self.make_ledger()
        evaluation_id = "eval-1"
        remote = "remote-1.wav"

        queued = ledger.upsert_queued_file(evaluation_id, remote, "/tmp/local.wav")
        queued_again = ledger.upsert_queued_file(
            evaluation_id, remote, "/tmp/different-local.wav"
        )
        self.assertEqual(queued.status, "queued")
        self.assertEqual(queued_again.status, "queued")
        self.assertEqual(queued_again.local_path, os.path.abspath("/tmp/local.wav"))

        md5 = ledger.mark_md5_ready(evaluation_id, remote, "abc==", 123)
        md5_again = ledger.mark_md5_ready(evaluation_id, remote, "abc==", 123)
        self.assertEqual(md5.status, "md5_ready")
        self.assertEqual(md5_again.status, "md5_ready")
        self.assertEqual(md5_again.content_md5, "abc==")
        self.assertEqual(md5_again.file_size, 123)

        uploaded = ledger.mark_uploaded(
            evaluation_id,
            remote,
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )
        registering = ledger.mark_metadata_registering(evaluation_id, remote)
        ledger.mark_metadata_registered(evaluation_id, remote)
        verified = ledger.mark_verified(evaluation_id, remote)

        self.assertEqual(uploaded.status, "uploaded")
        self.assertEqual(registering.status, "metadata_registering")
        self.assertEqual(verified.status, "verified")
        self.assertEqual(ledger.counts_by_status(evaluation_id)["verified"], 1)
        self.assertEqual(ledger.counts_by_status(evaluation_id)["queued"], 0)
        self.assertEqual(
            [row.remote_object_name for row in ledger.list_by_status(evaluation_id, "verified")],
            [remote],
        )

    def test_invalid_transition_does_not_advance_row(self):
        ledger, _ = self.make_ledger()
        ledger.upsert_queued_file("eval-1", "remote-1.wav", "/tmp/local.wav")

        with self.assertRaises(InvalidUploadLedgerTransition):
            ledger.mark_uploaded(
                "eval-1",
                "remote-1.wav",
                "2026-05-22T00:00:00.000Z",
                "2026-05-22T00:00:01.000Z",
            )

        self.assertEqual(ledger.get("eval-1", "remote-1.wav").status, "queued")  # type: ignore[union-attr]

    def test_transaction_rolls_back_on_failure(self):
        ledger, _ = self.make_ledger()
        ledger.upsert_queued_file("eval-1", "remote-1.wav", "/tmp/local.wav")

        with self.assertRaises(RuntimeError):
            with ledger._transaction() as conn:  # private helper intentionally probed for atomicity
                conn.execute(
                    """
                    UPDATE upload_ledger
                    SET status = 'uploaded', updated_at = 'broken'
                    WHERE evaluation_id = ? AND remote_object_name = ?
                    """,
                    ("eval-1", "remote-1.wav"),
                )
                raise RuntimeError("simulate crash after SQL update")

        row = ledger.get("eval-1", "remote-1.wav")
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "queued")  # type: ignore[union-attr]
        self.assertNotEqual(row.updated_at, "broken")  # type: ignore[union-attr]

    def test_connection_context_manager_closes_connection(self):
        ledger, _ = self.make_ledger()

        with ledger._connect() as conn:  # private helper guards Windows file cleanup
            conn.execute("SELECT 1").fetchone()

        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_concurrent_worker_style_updates_are_thread_safe(self):
        ledger, _ = self.make_ledger()
        evaluation_id = "eval-concurrent"
        total = 50

        def worker(index: int) -> None:
            remote = f"remote-{index:03d}.wav"
            ledger.upsert_queued_file(evaluation_id, remote, f"/tmp/{index}.wav")
            ledger.mark_md5_ready(evaluation_id, remote, f"md5-{index}", index + 1)
            ledger.mark_uploaded(
                evaluation_id,
                remote,
                "2026-05-22T00:00:00.000Z",
                "2026-05-22T00:00:01.000Z",
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(worker, range(total)))

        counts = ledger.counts_by_status(evaluation_id)
        self.assertEqual(counts["uploaded"], total)
        self.assertEqual(len(ledger.list_by_status(evaluation_id, "uploaded")), total)

    def test_busy_timeout_is_finite_when_database_is_locked(self):
        ledger, path = self.make_ledger(busy_timeout_ms=50)
        blocker = sqlite3.connect(path, timeout=1, isolation_level=None)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            start = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError):
                ledger.upsert_queued_file("eval-locked", "remote.wav", "/tmp/local.wav")
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 1.0)
        finally:
            blocker.rollback()
            blocker.close()

    def test_failure_statuses_store_actionable_errors(self):
        ledger, _ = self.make_ledger()
        ledger.upsert_queued_file("eval-1", "remote-1.wav", "/tmp/local.wav")
        failed_upload = ledger.mark_upload_failed(
            "eval-1", "remote-1.wav", "RuntimeError", "S3 PUT failed"
        )
        self.assertEqual(failed_upload.status, "upload_failed")
        self.assertEqual(failed_upload.error_type, "RuntimeError")
        self.assertEqual(failed_upload.error_message, "S3 PUT failed")

        ledger.upsert_queued_file("eval-1", "remote-2.wav", "/tmp/local-2.wav")
        ledger.mark_md5_ready("eval-1", "remote-2.wav", "abc==", 1)
        ledger.mark_uploaded(
            "eval-1",
            "remote-2.wav",
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )
        ledger.mark_metadata_registered("eval-1", "remote-2.wav")
        failed_verify = ledger.mark_verify_failed(
            "eval-1", "remote-2.wav", "VERIFY_FAILED", "expected bytes > 0"
        )
        self.assertEqual(failed_verify.status, "verify_failed")
        self.assertEqual(failed_verify.error_type, "VERIFY_FAILED")

    def test_uploaded_row_can_record_and_recover_verification_retry(self):
        ledger, _ = self.make_ledger()
        ledger.upsert_queued_file("eval-1", "remote-1.wav", "/tmp/local.wav")
        ledger.mark_md5_ready("eval-1", "remote-1.wav", "abc==", 123)
        ledger.mark_uploaded(
            "eval-1",
            "remote-1.wav",
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )

        failed_verify = ledger.mark_verify_failed(
            "eval-1", "remote-1.wav", "VERIFY_FAILED", "content mismatch"
        )
        self.assertEqual(failed_verify.status, "verify_failed")

        ledger.mark_md5_ready("eval-1", "remote-1.wav", "def==", 456)
        ledger.mark_uploaded(
            "eval-1",
            "remote-1.wav",
            "2026-05-22T00:01:00.000Z",
            "2026-05-22T00:01:01.000Z",
        )
        verified = ledger.mark_verified("eval-1", "remote-1.wav")
        self.assertEqual(verified.status, "verified")

    def test_failure_messages_are_redacted_before_storage(self):
        ledger, _ = self.make_ledger()
        ledger.upsert_queued_file("eval-1", "remote-1.wav", "/tmp/local.wav")

        failed_upload = ledger.mark_upload_failed(
            "eval-1",
            "remote-1.wav",
            "RuntimeError",
            "failed https://bucket.s3.amazonaws.com/a.wav?X-Amz-Signature=SECRET X-API-KEY=SECRET",
        )

        self.assertNotIn("SECRET", failed_upload.error_message)
        self.assertIn("[REDACTED]", failed_upload.error_message)

    def test_local_paths_are_persisted_as_absolute_paths(self):
        ledger, _ = self.make_ledger()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        previous_cwd = os.getcwd()
        try:
            os.chdir(temp_dir.name)
            queued = ledger.upsert_queued_file(
                "eval-1", "remote-1.wav", "relative.wav"
            )
            self.assertEqual(queued.local_path, os.path.abspath("relative.wav"))
            reset = ledger.reset_for_reupload(
                "eval-1", "remote-1.wav", "other-relative.wav"
            )
            self.assertEqual(reset.local_path, os.path.abspath("other-relative.wav"))
        finally:
            os.chdir(previous_cwd)

    def test_evaluation_contract_round_trips(self):
        ledger, _ = self.make_ledger()
        contract = {
            "evaluation_id": "eval-1",
            "eval_type": "NMOS",
            "eval_language": "en-us",
            "eval_batch_size": 1,
            "eval_template_id": None,
            "use_annotation": False,
            "use_loudness_normalization": True,
        }

        ledger.set_evaluation_contract("eval-1", contract)

        self.assertEqual(ledger.get_evaluation_contract("eval-1"), contract)

    def test_finalization_hashes_gate_process_and_session_replay_skips(self):
        ledger, _ = self.make_ledger()

        ledger.mark_processed("eval-1", 2, request_hash="process-hash-a")
        ledger.mark_session_json_uploaded("eval-1", session_json_hash="session-hash-a")

        self.assertTrue(ledger.is_processed("eval-1"))
        self.assertTrue(ledger.is_processed("eval-1", "process-hash-a"))
        self.assertFalse(ledger.is_processed("eval-1", "process-hash-b"))
        self.assertTrue(ledger.is_session_json_uploaded("eval-1"))
        self.assertTrue(ledger.is_session_json_uploaded("eval-1", "session-hash-a"))
        self.assertFalse(ledger.is_session_json_uploaded("eval-1", "session-hash-b"))

    def test_manifest_key_reorders_without_collapsing_duplicate_occurrences(self):
        ledger, _ = self.make_ledger()
        first = ledger.upsert_queued_file(
            "eval-1",
            "remote-1.wav",
            "/tmp/local-1.wav",
            file_index=0,
            manifest_key="manifest-1",
        )
        same_manifest_different_index = ledger.upsert_queued_file(
            "eval-1",
            "remote-2.wav",
            "/tmp/local-2.wav",
            file_index=1,
            manifest_key="manifest-1",
        )

        self.assertNotEqual(
            same_manifest_different_index.remote_object_name,
            first.remote_object_name,
        )

        third = ledger.upsert_queued_file(
            "eval-1",
            "remote-3.wav",
            "/tmp/local-3.wav",
            file_index=2,
            manifest_key="manifest-2",
        )
        reordered_third = ledger.upsert_queued_file(
            "eval-1",
            "remote-3-reordered.wav",
            "/tmp/local-3.wav",
            file_index=0,
            manifest_key="manifest-2",
        )

        self.assertEqual(reordered_third.remote_object_name, third.remote_object_name)
        with self.assertRaises(ValueError):
            ledger.upsert_queued_file(
                "eval-1",
                "remote-4.wav",
                "/tmp/local-4.wav",
                file_index=0,
                manifest_key="different-manifest",
            )

    def test_build_upload_manifest_key_ignores_remote_object_identity(self):
        key_a = build_upload_manifest_key(
            {"uploaded_file_name": "remote-a.wav", "model_tag": "model-a"},
            "md5",
            10,
        )
        key_b = build_upload_manifest_key(
            {"uploaded_file_name": "remote-b.wav", "model_tag": "model-a"},
            "md5",
            10,
        )

        self.assertEqual(key_a, key_b)

    def test_legacy_duplicate_file_indexes_are_supported_after_migration(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = os.path.join(temp_dir.name, "legacy-state.sqlite")
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE upload_ledger (
                    evaluation_id TEXT NOT NULL,
                    remote_object_name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    file_index INTEGER,
                    status TEXT NOT NULL,
                    content_md5 TEXT,
                    file_size INTEGER,
                    upload_start_at TEXT,
                    upload_finish_at TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (evaluation_id, remote_object_name)
                );
                INSERT INTO upload_ledger (
                    evaluation_id, remote_object_name, local_path, file_index,
                    status, created_at, updated_at
                ) VALUES
                  ('eval-1', 'remote-1.wav', '/tmp/1.wav', 0, 'queued', 'now', 'now'),
                  ('eval-1', 'remote-2.wav', '/tmp/2.wav', 0, 'queued', 'now', 'now');
                """
            )
            conn.commit()
        finally:
            conn.close()

        ledger = UploadLedger(path)

        with ledger._transaction() as migrated:
            rows = migrated.execute(
                """
                SELECT remote_object_name, file_index
                FROM upload_ledger
                WHERE evaluation_id = 'eval-1'
                ORDER BY remote_object_name
                """
            ).fetchall()
        self.assertEqual([row["file_index"] for row in rows].count(0), 2)

        with ledger._transaction() as migrated:
            migrated.execute(
                """
                INSERT INTO upload_ledger (
                    evaluation_id,
                    remote_object_name,
                    local_path,
                    file_index,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "eval-1",
                    "remote-3.wav",
                    "/tmp/3.wav",
                    0,
                    "queued",
                    "now",
                    "now",
                ),
            )

    @unittest.skipIf(os.name == "nt", "POSIX symlink check")
    def test_ledger_rejects_symlink_path(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        target_path = os.path.join(temp_dir.name, "target.sqlite")
        symlink_path = os.path.join(temp_dir.name, "upload-state.sqlite")
        with open(target_path, "wb") as f:
            f.write(b"")
        os.symlink(target_path, symlink_path)

        with self.assertRaises(ValueError):
            UploadLedger(symlink_path)

    @unittest.skipIf(os.name == "nt", "POSIX symlink check")
    def test_ledger_rejects_symlink_parent_path(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = os.path.realpath(temp_dir.name)
        real_parent = os.path.join(root, "real-parent")
        symlink_parent = os.path.join(root, "linked-parent")
        os.makedirs(real_parent)
        os.symlink(real_parent, symlink_parent)

        with self.assertRaises(ValueError):
            UploadLedger(os.path.join(symlink_parent, "upload-state.sqlite"))

    @unittest.skipIf(os.name == "nt", "POSIX file mode check")
    def test_ledger_file_permissions_are_owner_only(self):
        _, path = self.make_ledger()

        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_mark_metadata_registered_sets_metadata_acked(self):
        ledger, _ = self.make_ledger()
        e, r = "eval-1", "remote-1.wav"
        ledger.upsert_queued_file(e, r, "/tmp/local.wav")
        ledger.mark_md5_ready(e, r, "abc==", 123)
        ledger.mark_uploaded(e, r, "2026-05-22T00:00:00.000Z", "2026-05-22T00:00:01.000Z")
        self.assertFalse(ledger.get(e, r).metadata_acked)  # type: ignore[union-attr]
        registered = ledger.mark_metadata_registered(e, r)
        self.assertTrue(registered.metadata_acked)

    def test_metadata_acked_is_monotonic_across_status_churn(self):
        ledger, _ = self.make_ledger()
        e, r = "eval-1", "remote-1.wav"
        ledger.upsert_queued_file(e, r, "/tmp/local.wav")
        ledger.mark_md5_ready(e, r, "abc==", 123)
        ledger.mark_uploaded(e, r, "2026-05-22T00:00:00.000Z", "2026-05-22T00:00:01.000Z")
        ledger.mark_metadata_registered(e, r)
        # metadata_registered -> verify_failed -> md5_ready -> uploaded must keep ack
        ledger.mark_verify_failed(e, r, "VERIFY_FAILED", "bad")
        self.assertTrue(ledger.get(e, r).metadata_acked)  # type: ignore[union-attr]
        ledger.mark_md5_ready(e, r, "def==", 456)
        ledger.mark_uploaded(e, r, "2026-05-22T00:01:00.000Z", "2026-05-22T00:01:01.000Z")
        self.assertTrue(ledger.get(e, r).metadata_acked)  # type: ignore[union-attr]
        # reset_for_reupload must not clear the monotonic ack either
        ledger.reset_for_reupload(e, r, "/tmp/local.wav")
        self.assertTrue(ledger.get(e, r).metadata_acked)  # type: ignore[union-attr]

    def test_migration_backfills_metadata_acked_for_registered_and_verified(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = os.path.join(temp_dir.name, "prefix-state.sqlite")
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
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
                        'queued','md5_ready','uploaded','metadata_registering',
                        'metadata_registered','verified','upload_failed','verify_failed'
                    ))
                );
                INSERT INTO upload_ledger
                    (evaluation_id, remote_object_name, local_path, status, created_at, updated_at)
                VALUES
                    ('eval-1','r-queued.wav','/tmp/q.wav','queued','now','now'),
                    ('eval-1','r-uploaded.wav','/tmp/u.wav','uploaded','now','now'),
                    ('eval-1','r-registering.wav','/tmp/rg.wav','metadata_registering','now','now'),
                    ('eval-1','r-registered.wav','/tmp/rd.wav','metadata_registered','now','now'),
                    ('eval-1','r-verified.wav','/tmp/v.wav','verified','now','now');
                """
            )
            conn.commit()
        finally:
            conn.close()

        ledger = UploadLedger(path)

        def acked(remote: str) -> bool:
            return ledger.get("eval-1", remote).metadata_acked  # type: ignore[union-attr]

        # provably-already-POSTed rows are backfilled
        self.assertTrue(acked("r-registered.wav"))
        self.assertTrue(acked("r-verified.wav"))
        # everything else (including the unconfirmed metadata_registering) stays false
        self.assertFalse(acked("r-queued.wav"))
        self.assertFalse(acked("r-uploaded.wav"))
        self.assertFalse(acked("r-registering.wav"))

        # backfill is idempotent: re-opening does not change anything
        reopened = UploadLedger(path)
        self.assertTrue(reopened.get("eval-1", "r-verified.wav").metadata_acked)  # type: ignore[union-attr]
        self.assertFalse(reopened.get("eval-1", "r-registering.wav").metadata_acked)  # type: ignore[union-attr]

    def test_migration_backfills_metadata_acked_through_table_rebuild(self):
        # Exercises the COMBINED path: an ancient table with NO metadata_registering
        # CHECK (forces _migrate_status_check_if_needed to rebuild) AND no
        # metadata_acked column. The rebuild must project metadata_acked via
        # CASE EXISTS(...), then the backfill must set registered/verified -> 1.
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = os.path.join(temp_dir.name, "ancient-state.sqlite")
        conn = sqlite3.connect(path)
        try:
            conn.executescript(
                """
                CREATE TABLE upload_ledger (
                    evaluation_id TEXT NOT NULL,
                    remote_object_name TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    file_index INTEGER,
                    status TEXT NOT NULL,
                    content_md5 TEXT,
                    file_size INTEGER,
                    upload_start_at TEXT,
                    upload_finish_at TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (evaluation_id, remote_object_name)
                );
                INSERT INTO upload_ledger
                    (evaluation_id, remote_object_name, local_path, status, created_at, updated_at)
                VALUES
                    ('eval-1','r-registered.wav','/tmp/rd.wav','metadata_registered','now','now'),
                    ('eval-1','r-verified.wav','/tmp/v.wav','verified','now','now'),
                    ('eval-1','r-queued.wav','/tmp/q.wav','queued','now','now');
                """
            )
            conn.commit()
        finally:
            conn.close()

        ledger = UploadLedger(path)
        # rebuild happened (the new CHECK now permits metadata_registering)
        ledger.upsert_queued_file("eval-1", "r-new.wav", "/tmp/n.wav")
        ledger.mark_md5_ready("eval-1", "r-new.wav", "abc==", 1)
        ledger.mark_uploaded("eval-1", "r-new.wav", "t0", "t1")
        self.assertEqual(
            ledger.mark_metadata_registering("eval-1", "r-new.wav").status,
            "metadata_registering",
        )
        # backfill survived the rebuild
        self.assertTrue(ledger.get("eval-1", "r-registered.wav").metadata_acked)  # type: ignore[union-attr]
        self.assertTrue(ledger.get("eval-1", "r-verified.wav").metadata_acked)  # type: ignore[union-attr]
        self.assertFalse(ledger.get("eval-1", "r-queued.wav").metadata_acked)  # type: ignore[union-attr]

    def test_stable_manifest_contract_is_stable_across_group_id_regen(self):
        run1 = {
            "uploaded_file_name": "a.wav",
            "model_tag": "m",
            "group": "1700000000000_uuid-A",
            "order_in_group": 0,
        }
        run2 = {
            "uploaded_file_name": "b.wav",
            "model_tag": "m",
            "group": "1700000001111_uuid-B",
            "order_in_group": 0,
        }
        key1 = build_upload_manifest_key(stable_manifest_contract(run1, 0), "md5", 10)
        key2 = build_upload_manifest_key(stable_manifest_contract(run2, 0), "md5", 10)
        # different random group_id, same positional ordinal -> same identity
        self.assertEqual(key1, key2)
        # different ordinal (a distinct group) -> distinct identity (#318 preserved)
        key_other = build_upload_manifest_key(
            stable_manifest_contract(run1, 1), "md5", 10
        )
        self.assertNotEqual(key1, key_other)
        # no ordinal -> raw identity kept unchanged (isolated callers / no group key)
        raw = build_upload_manifest_key(run1, "md5", 10)
        self.assertEqual(
            build_upload_manifest_key(stable_manifest_contract(run1, None), "md5", 10),
            raw,
        )
        no_group = {"uploaded_file_name": "a.wav", "model_tag": "m"}
        self.assertEqual(stable_manifest_contract(no_group, 3), no_group)

    def test_stable_manifest_contract_preserves_none_group_for_backward_compat(self):
        # Single-stimulus rows carry group=None, which is already a stable constant.
        # Substituting it to an ordinal would change the manifest identity and break
        # resume of ledgers written by prior SDK versions (stored with group=None).
        single = {
            "uploaded_file_name": "a.wav",
            "model_tag": "m",
            "group": None,
            "order_in_group": 0,
        }
        # even with a resolved ordinal, a None group is left untouched
        self.assertIsNone(stable_manifest_contract(single, 0)["group"])
        legacy_key = build_upload_manifest_key(single, "md5", 10)
        self.assertEqual(
            build_upload_manifest_key(stable_manifest_contract(single, 0), "md5", 10),
            legacy_key,
        )


if __name__ == "__main__":
    unittest.main()
