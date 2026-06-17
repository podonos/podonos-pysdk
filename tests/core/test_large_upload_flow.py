import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import MagicMock, Mock, patch

from podonos.common.enum import EvalType, QuestionFileType
from podonos.common.util import calculate_file_md5_base64
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import Audio, File
from podonos.core.upload_ledger import (
    build_upload_manifest_hash,
    build_upload_manifest_key,
    stable_manifest_contract,
)
from podonos.service.evaluation_service import EvaluationService
from podonos.entity.evaluation import EvaluationEntity
from podonos.entity.verification import (
    FileVerificationResult,
    VerificationErrorDetail,
    VerifyFilesResponse,
)

TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")


@dataclass
class FakeAudio:
    path: str
    remote_object_name: str
    is_silent: bool = False
    # group/order_in_group exist so the c3 idempotency key and the group-ordinal
    # resolution work against the double. to_create_file_dict() stays minimal (no
    # "group" key) on purpose: stable_manifest_contract only substitutes when a
    # "group" key is present, so seeded manifest hashes stay byte-stable.
    group: Optional[str] = None
    order_in_group: int = 0

    def to_create_file_dict(self):
        return {"uploaded_file_name": self.remote_object_name, "original_name": self.path}

    def set_integrity_info(self, content_md5: str, file_size: int) -> None:
        self.content_md5 = content_md5
        self.file_size = file_size

    def set_upload_at(self, start_at: str, finish_at: str) -> None:
        self.upload_start_at = start_at
        self.upload_finish_at = finish_at


@dataclass
class FakeGroup:
    """Minimal AudioGroup stand-in carrying its audios (and an optional group_id),
    used to model the realistic one-group-per-single-stimulus-file layout so the
    positional group ordinal resolves to distinct values."""

    audios: List["FakeAudio"]
    group_id: Optional[str] = None


class TestLargeUploadLedgerFlow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_path = os.path.join(self.temp_dir.name, "upload-state.sqlite")
        self.evaluation = EvaluationEntity(
            id="eval-ledger",
            title="title",
            internal_name=None,
            description=None,
            batch_size=1,
            status="DRAFT",
            created_time=datetime.now(timezone.utc),
            updated_time=datetime.now(timezone.utc),
        )

    def make_evaluator(self, resume_upload: bool = True) -> Evaluator:
        config = EvalConfig(
            type=EvalType.NMOS.value,
            verify_batch_size=100,
            resume_upload=resume_upload,
            upload_state_path=self.state_path,
        )
        with patch.object(Evaluator, "_set_evaluation", return_value=self.evaluation):
            evaluator = Evaluator(
                api_client=Mock(spec=APIClient),
                eval_config=config,
                supported_eval_types=EvalType.get_single_types(),
            )
        return evaluator

    def fake_audios(self, count: int, prefix: str = "remote") -> List[FakeAudio]:
        return [
            FakeAudio(TESTDATA_SPEECH_CH1_MP3, f"{prefix}-{i:05d}.wav")
            for i in range(count)
        ]

    def seed_rows(self, evaluator: Evaluator, audios: List[FakeAudio], status: str) -> None:
        assert evaluator._upload_ledger is not None  # type: ignore[attr-defined]
        now = "2026-05-22T00:00:00.000Z"
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)
        for audio in audios:
            audio.set_integrity_info(content_md5, file_size)
        with evaluator._upload_ledger._transaction() as conn:  # type: ignore[union-attr]
            conn.executemany(
                """
                INSERT INTO upload_ledger (
                    evaluation_id,
                    remote_object_name,
                    local_path,
                    status,
                    content_md5,
                    file_size,
                    manifest_key,
                    manifest_hash,
                    upload_start_at,
                    upload_finish_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        evaluator.get_evaluation_id(),
                        audio.remote_object_name,
                        audio.path,
                        status,
                        content_md5,
                        file_size,
                        build_upload_manifest_key(
                            audio.to_create_file_dict(), content_md5, file_size
                        ),
                        build_upload_manifest_hash(
                            audio.to_create_file_dict(), content_md5, file_size
                        ),
                        now,
                        now,
                        now,
                        now,
                    )
                    for audio in audios
                ],
            )

    def configure_verify_all_success(self, evaluator: Evaluator) -> MagicMock:
        service = MagicMock()
        service.process_files.return_value = SimpleNamespace(processing_count=0)

        def verify_files(evaluation_id, audios, **kwargs):
            return VerifyFilesResponse(
                all_verified=True,
                verified_count=len(audios),
                failed_count=0,
                results=[
                    FileVerificationResult(
                        uploaded_file_name=audio.remote_object_name,
                        verified=True,
                        file_meta_id=f"meta-{index}",
                        error=None,
                    )
                    for index, audio in enumerate(audios)
                ],
            )

        service.verify_files.side_effect = verify_files
        evaluator._evaluation_service = service  # type: ignore[assignment]
        return service

    def test_5k_fake_flow_registers_metadata_verifies_and_bounds_success_results(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(5000)
        self.seed_rows(evaluator, audios, "uploaded")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        self.assertEqual(service.create_evaluation_files.call_count, 10)
        self.assertEqual(service.verify_files.call_count, 50)
        self.assertEqual(
            evaluator._upload_ledger.counts_by_status(evaluator.get_evaluation_id())["verified"],  # type: ignore[union-attr]
            5000,
        )

        response = evaluator._verify_files_in_batches(evaluator.get_evaluation_id(), audios)  # type: ignore[arg-type]
        self.assertTrue(response.all_verified)
        self.assertEqual(response.verified_count, 5000)
        self.assertEqual(response.results, [])

    def test_duplicate_identical_files_do_not_collapse_ledger_identity(self):
        evaluator = self.make_evaluator()
        evaluator._evaluation_service.get_presigned_url = MagicMock(  # type: ignore[method-assign]
            return_value="https://example.com/presigned-url"
        )
        evaluator._evaluation_service.upload_evaluation_file = MagicMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )
        duplicate_file = File(path=TESTDATA_SPEECH_CH1_MP3, model_tag="same-model")

        evaluator.add_file(duplicate_file)
        evaluator.add_file(duplicate_file)
        evaluator._wait_for_uploads()

        assert evaluator._upload_ledger is not None
        uploaded_rows = evaluator._upload_ledger.list_by_status(
            evaluator.get_evaluation_id(), "uploaded"
        )
        self.assertEqual(len(uploaded_rows), 2)
        self.assertEqual(
            len({row.remote_object_name for row in uploaded_rows}),
            2,
        )
        self.assertEqual(
            evaluator._evaluation_service.upload_evaluation_file.call_count,  # type: ignore[attr-defined]
            2,
        )

    def test_interrupted_resume_skips_verified_and_partial_metadata(self):
        evaluator = self.make_evaluator()
        verified = self.fake_audios(1, prefix="verified")
        metadata_registered = self.fake_audios(1, prefix="registered")
        uploaded = self.fake_audios(1, prefix="uploaded")
        self.seed_rows(evaluator, verified, "verified")
        self.seed_rows(evaluator, metadata_registered, "metadata_registered")
        self.seed_rows(evaluator, uploaded, "uploaded")
        audios = verified + metadata_registered + uploaded
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.create_evaluation_files.assert_called_once()
        registered_batch = service.create_evaluation_files.call_args.args[1]
        self.assertEqual([audio.remote_object_name for audio in registered_batch], [uploaded[0].remote_object_name])
        service.verify_files.assert_called_once()
        verified_batch = service.verify_files.call_args.args[1]
        self.assertEqual(
            {audio.remote_object_name for audio in verified_batch},
            {metadata_registered[0].remote_object_name, uploaded[0].remote_object_name},
        )
        self.assertEqual(
            evaluator._upload_ledger.counts_by_status(evaluator.get_evaluation_id())["verified"],  # type: ignore[union-attr]
            3,
        )

    def test_metadata_registering_resume_verifies_before_reregistering(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(2, prefix="registering")
        self.seed_rows(evaluator, audios, "metadata_registering")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.create_evaluation_files.assert_not_called()
        service.verify_files.assert_called_once()
        self.assertEqual(
            evaluator._upload_ledger.counts_by_status(evaluator.get_evaluation_id())["verified"],  # type: ignore[union-attr]
            2,
        )

    def test_metadata_registering_verification_failure_retries_metadata_not_upload(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="registering-missing")
        self.seed_rows(evaluator, audios, "metadata_registering")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]

        service = MagicMock()
        service.process_files.return_value = SimpleNamespace(processing_count=0)
        service.verify_files.side_effect = [
            VerifyFilesResponse(
                all_verified=False,
                verified_count=0,
                failed_count=1,
                results=[
                    FileVerificationResult(
                        audios[0].remote_object_name,
                        False,
                        None,
                        VerificationErrorDetail(
                            code="METADATA_NOT_FOUND",
                            message="metadata is not registered",
                            expected=None,
                            actual=None,
                        ),
                    )
                ],
            ),
            VerifyFilesResponse(
                all_verified=True,
                verified_count=1,
                failed_count=0,
                results=[
                    FileVerificationResult(
                        audios[0].remote_object_name,
                        True,
                        "meta-0",
                        None,
                    )
                ],
            ),
        ]
        evaluator._evaluation_service = service  # type: ignore[assignment]

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.create_evaluation_files.assert_called_once()
        service.get_presigned_url.assert_not_called()
        service.upload_evaluation_file.assert_not_called()
        self.assertEqual(
            evaluator._upload_ledger.get(  # type: ignore[union-attr]
                evaluator.get_evaluation_id(), audios[0].remote_object_name
            ).status,
            "verified",
        )

    def test_upload_retry_registers_metadata_before_reverification(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="upload-retry-metadata")
        self.seed_rows(evaluator, audios, "metadata_registered")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]

        service = evaluator._evaluation_service
        service.process_files = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(processing_count=0)
        )
        service.get_presigned_url = MagicMock(  # type: ignore[method-assign]
            return_value="https://example.com/presigned-url"
        )
        service.upload_evaluation_file = MagicMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )
        service.create_evaluation_files = MagicMock()  # type: ignore[method-assign]
        failure_response = VerifyFilesResponse(
            all_verified=False,
            verified_count=0,
            failed_count=1,
            results=[
                FileVerificationResult(
                    audios[0].remote_object_name,
                    False,
                    None,
                    VerificationErrorDetail(
                        code="METADATA_NOT_FOUND",
                        message="metadata missing after upload",
                        expected=None,
                        actual=None,
                    ),
                )
            ],
        )
        success_response = VerifyFilesResponse(
            all_verified=True,
            verified_count=1,
            failed_count=0,
            results=[
                FileVerificationResult(
                    audios[0].remote_object_name,
                    True,
                    "meta-after-retry",
                    None,
                )
            ],
        )

        def verify_after_metadata_retry(*args, **kwargs):
            if service.verify_files.call_count == 1:  # type: ignore[attr-defined]
                return failure_response
            self.assertTrue(service.create_evaluation_files.called)  # type: ignore[attr-defined]
            return success_response

        service.verify_files = MagicMock(  # type: ignore[method-assign]
            side_effect=verify_after_metadata_retry
        )

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.upload_evaluation_file.assert_called_once()
        service.create_evaluation_files.assert_called_once()
        self.assertEqual(service.verify_files.call_count, 2)

    def test_metadata_registration_create_failure_rolls_back_to_uploaded(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(2, prefix="metadata-timeout")
        self.seed_rows(evaluator, audios, "uploaded")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = MagicMock()
        service.process_files.return_value = SimpleNamespace(processing_count=0)
        service.create_evaluation_files.side_effect = RuntimeError(
            "create timed out client_secret=SECRET"
        )
        evaluator._evaluation_service = service  # type: ignore[assignment]

        with self.assertRaises(RuntimeError):
            evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        assert evaluator._upload_ledger is not None
        for audio in audios:
            row = evaluator._upload_ledger.get(
                evaluator.get_evaluation_id(), audio.remote_object_name
            )
            self.assertEqual(row.status, "uploaded")  # type: ignore[union-attr]
            self.assertNotIn("SECRET", row.error_message)  # type: ignore[union-attr]
        service.verify_files.assert_not_called()
        service.get_presigned_url.assert_not_called()
        service.upload_evaluation_file.assert_not_called()

    def test_metadata_registration_skips_ledger_mark_for_missing_rows(self):
        evaluator = self.make_evaluator()
        missing_row_audio = self.fake_audios(1, prefix="missing-ledger")[0]
        uploaded_audio = self.fake_audios(1, prefix="uploaded-ledger")[0]
        self.seed_rows(evaluator, [uploaded_audio], "uploaded")
        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]

        evaluator._register_metadata_for_audios([missing_row_audio, uploaded_audio])  # type: ignore[arg-type]

        service.create_evaluation_files.assert_called_once()
        registered_batch = service.create_evaluation_files.call_args.args[1]
        self.assertEqual(
            [audio.remote_object_name for audio in registered_batch],
            [missing_row_audio.remote_object_name, uploaded_audio.remote_object_name],
        )
        assert evaluator._upload_ledger is not None
        self.assertIsNone(
            evaluator._upload_ledger.get(
                evaluator.get_evaluation_id(), missing_row_audio.remote_object_name
            )
        )
        uploaded_row = evaluator._upload_ledger.get(
            evaluator.get_evaluation_id(), uploaded_audio.remote_object_name
        )
        self.assertEqual(uploaded_row.status, "metadata_registered")  # type: ignore[union-attr]

    def test_processed_finalization_skips_backend_process_replay(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(2, prefix="finalized")
        self.seed_rows(evaluator, audios, "verified")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)
        assert evaluator._upload_ledger is not None
        request_hash = evaluator._finalization_hash(  # type: ignore[attr-defined]
            {
                "evaluation_id": evaluator.get_evaluation_id(),
                "files": [audio.to_create_file_dict() for audio in audios],
            }
        )
        evaluator._upload_ledger.mark_processed(
            evaluator.get_evaluation_id(), 2, request_hash
        )

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.process_files.assert_not_called()

    def test_processed_finalization_hash_mismatch_replays_backend_process(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(2, prefix="changed-finalized")
        self.seed_rows(evaluator, audios, "verified")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.mark_processed(
            evaluator.get_evaluation_id(), 2, "different-request-hash"
        )

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.process_files.assert_called_once()

    def test_process_success_records_finalization_state(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="process-finalized")
        self.seed_rows(evaluator, audios, "verified")
        evaluator._ordered_file_groups = [SimpleNamespace(audios=audios)]  # type: ignore[assignment]
        service = self.configure_verify_all_success(evaluator)

        evaluator._process_audio_files_with_verification()  # type: ignore[arg-type]

        service.process_files.assert_called_once()
        assert evaluator._upload_ledger is not None
        self.assertTrue(
            evaluator._upload_ledger.is_processed(evaluator.get_evaluation_id())
        )

    def test_session_json_finalization_skips_reupload(self):
        evaluator = self.make_evaluator()
        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.mark_session_json_uploaded(
            evaluator.get_evaluation_id(),
            evaluator._finalization_hash(evaluator._session_json_payload()),  # type: ignore[attr-defined]
        )

        evaluator._upload_session_json()  # type: ignore[attr-defined]

        service.upload_session_json.assert_not_called()

    def test_session_json_finalization_hash_mismatch_reuploads(self):
        evaluator = self.make_evaluator()
        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.mark_session_json_uploaded(
            evaluator.get_evaluation_id(), "different-session-json-hash"
        )

        evaluator._upload_session_json()  # type: ignore[attr-defined]

        service.upload_session_json.assert_called_once()

    def test_stable_manifest_identity_prevents_order_based_remote_misbind(self):
        evaluator = self.make_evaluator()
        audio_path = TESTDATA_SPEECH_CH1_MP3
        old_a = Audio(
            path=audio_path,
            name="speech_ch1.mp3",
            remote_object_name="old-a.wav",
            script="script-a",
            tags=["tag-a"],
            model_tag="model-a",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        old_b = Audio(
            path=audio_path,
            name="speech_ch1.mp3",
            remote_object_name="old-b.wav",
            script="script-b",
            tags=["tag-b"],
            model_tag="model-b",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        assert evaluator._upload_ledger is not None
        content_md5, file_size = calculate_file_md5_base64(audio_path)
        for index, audio in enumerate([old_a, old_b]):
            audio.set_integrity_info(content_md5, file_size)
            manifest_key = build_upload_manifest_key(
                audio.to_create_file_dict(), content_md5, file_size
            )
            manifest_hash = build_upload_manifest_hash(
                audio.to_create_file_dict(), content_md5, file_size
            )
            evaluator._upload_ledger.upsert_queued_file(
                evaluator.get_evaluation_id(),
                audio.remote_object_name,
                audio.path,
                file_index=index,
                manifest_key=manifest_key,
            )
            evaluator._upload_ledger.mark_md5_ready(
                evaluator.get_evaluation_id(),
                audio.remote_object_name,
                content_md5,
                file_size,
                manifest_key=manifest_key,
                manifest_hash=manifest_hash,
            )
            evaluator._upload_ledger.mark_uploaded(
                evaluator.get_evaluation_id(),
                audio.remote_object_name,
                "2026-05-22T00:00:00.000Z",
                "2026-05-22T00:00:01.000Z",
            )
            evaluator._upload_ledger.mark_metadata_registered(
                evaluator.get_evaluation_id(), audio.remote_object_name
            )
            evaluator._upload_ledger.mark_verified(
                evaluator.get_evaluation_id(), audio.remote_object_name
            )

        new_b = Audio(
            path=audio_path,
            name="speech_ch1.mp3",
            remote_object_name="new-b.wav",
            script="script-b",
            tags=["tag-b"],
            model_tag="model-b",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        new_a = Audio(
            path=audio_path,
            name="speech_ch1.mp3",
            remote_object_name="new-a.wav",
            script="script-a",
            tags=["tag-a"],
            model_tag="model-a",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        self.assertTrue(evaluator._should_skip_upload(new_b))  # type: ignore[attr-defined]
        self.assertEqual(new_b.remote_object_name, "old-b.wav")
        self.assertTrue(evaluator._should_skip_upload(new_a))  # type: ignore[attr-defined]
        self.assertEqual(new_a.remote_object_name, "old-a.wav")

    def test_verified_ledger_row_rejects_changed_local_file(self):
        evaluator = self.make_evaluator()
        local_path = os.path.join(self.temp_dir.name, "changed.wav")
        with open(local_path, "wb") as f:
            f.write(b"original")

        audio = FakeAudio(local_path, "changed-remote.wav")
        assert evaluator._upload_ledger is not None
        content_md5, file_size = calculate_file_md5_base64(local_path)
        evaluator._upload_ledger.upsert_queued_file(
            evaluator.get_evaluation_id(), audio.remote_object_name, audio.path
        )
        evaluator._upload_ledger.mark_md5_ready(
            evaluator.get_evaluation_id(), audio.remote_object_name, content_md5, file_size
        )
        evaluator._upload_ledger.mark_uploaded(
            evaluator.get_evaluation_id(),
            audio.remote_object_name,
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )
        evaluator._upload_ledger.mark_metadata_registering(
            evaluator.get_evaluation_id(), audio.remote_object_name
        )
        evaluator._upload_ledger.mark_metadata_registered(
            evaluator.get_evaluation_id(), audio.remote_object_name
        )
        evaluator._upload_ledger.mark_verified(
            evaluator.get_evaluation_id(), audio.remote_object_name
        )

        with open(local_path, "wb") as f:
            f.write(b"changed")

        with self.assertRaises(ValueError):
            evaluator._verify_files_in_batches(evaluator.get_evaluation_id(), [audio])  # type: ignore[arg-type]

    def test_verified_ledger_row_rejects_changed_file_metadata_contract(self):
        evaluator = self.make_evaluator()
        old_audio = Audio(
            path=TESTDATA_SPEECH_CH1_MP3,
            name="speech_ch1.mp3",
            remote_object_name="metadata-contract.mp3",
            script="original script",
            tags=["original-tag"],
            model_tag="old-model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        new_audio = Audio(
            path=TESTDATA_SPEECH_CH1_MP3,
            name="speech_ch1.mp3",
            remote_object_name="metadata-contract.mp3",
            script="changed script",
            tags=["changed-tag"],
            model_tag="new-model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        assert evaluator._upload_ledger is not None
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)
        old_audio.set_integrity_info(content_md5, file_size)
        evaluator._upload_ledger.upsert_queued_file(
            evaluator.get_evaluation_id(), old_audio.remote_object_name, old_audio.path
        )
        evaluator._upload_ledger.mark_md5_ready(
            evaluator.get_evaluation_id(),
            old_audio.remote_object_name,
            content_md5,
            file_size,
            manifest_hash=build_upload_manifest_hash(
                old_audio.to_create_file_dict(), content_md5, file_size
            ),
        )
        evaluator._upload_ledger.mark_uploaded(
            evaluator.get_evaluation_id(),
            old_audio.remote_object_name,
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )
        evaluator._upload_ledger.mark_metadata_registered(
            evaluator.get_evaluation_id(), old_audio.remote_object_name
        )
        evaluator._upload_ledger.mark_verified(
            evaluator.get_evaluation_id(), old_audio.remote_object_name
        )

        with self.assertRaises(ValueError):
            evaluator._verify_files_in_batches(evaluator.get_evaluation_id(), [new_audio])

    def test_ledger_verification_does_not_aggregate_success_results(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(250, prefix="success")
        self.seed_rows(evaluator, audios, "metadata_registered")
        service = self.configure_verify_all_success(evaluator)

        response = evaluator._verify_files_in_batches(evaluator.get_evaluation_id(), audios)  # type: ignore[arg-type]

        self.assertEqual(service.verify_files.call_count, 3)
        self.assertTrue(response.all_verified)
        self.assertEqual(response.verified_count, 250)
        self.assertEqual(response.failed_count, 0)
        self.assertEqual(response.results, [])

    def test_verify_failed_status_is_persisted_and_retry_can_verify(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(2)
        self.seed_rows(evaluator, audios, "metadata_registered")
        service = MagicMock()
        service.verify_files.return_value = VerifyFilesResponse(
            all_verified=False,
            verified_count=1,
            failed_count=1,
            results=[
                FileVerificationResult(audios[0].remote_object_name, True, "meta-0", None),
                FileVerificationResult(
                    audios[1].remote_object_name,
                    False,
                    None,
                    VerificationErrorDetail(
                        code="SIZE_MISMATCH",
                        message="expected bytes > 0",
                        expected="1",
                        actual="0",
                    ),
                ),
            ],
        )
        evaluator._evaluation_service = service  # type: ignore[assignment]

        response = evaluator._verify_files_in_batches(evaluator.get_evaluation_id(), audios)  # type: ignore[arg-type]

        self.assertFalse(response.all_verified)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(
            evaluator._upload_ledger.get(evaluator.get_evaluation_id(), audios[1].remote_object_name).status,  # type: ignore[union-attr]
            "verify_failed",
        )

        service.verify_files.return_value = VerifyFilesResponse(
            all_verified=True,
            verified_count=1,
            failed_count=0,
            results=[
                FileVerificationResult(audios[1].remote_object_name, True, "meta-1", None)
            ],
        )
        retry_response = evaluator._verify_files_in_batches(  # type: ignore[arg-type]
            evaluator.get_evaluation_id(), [audios[1]]
        )
        self.assertTrue(retry_response.all_verified)
        self.assertEqual(
            evaluator._upload_ledger.counts_by_status(evaluator.get_evaluation_id())["verified"],  # type: ignore[union-attr]
            2,
        )

    def test_upload_failed_row_is_retried_and_marked_uploaded(self):
        evaluator = self.make_evaluator()
        audio = Audio(
            path=TESTDATA_SPEECH_CH1_MP3,
            name="speech_ch1.mp3",
            remote_object_name="remote-retry.mp3",
            script=None,
            tags=[],
            model_tag="model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.upsert_queued_file(
            evaluator.get_evaluation_id(), audio.remote_object_name, audio.path
        )
        evaluator._upload_ledger.mark_upload_failed(
            evaluator.get_evaluation_id(), audio.remote_object_name, "RuntimeError", "first upload failed"
        )
        evaluator._evaluation_service.get_presigned_url = MagicMock(  # type: ignore[method-assign]
            return_value="https://example.com/presigned-url"
        )
        evaluator._evaluation_service.upload_evaluation_file = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]

        evaluator._upload_one_file(evaluator.get_evaluation_id(), audio)
        evaluator._wait_for_uploads()

        row = evaluator._upload_ledger.get(evaluator.get_evaluation_id(), audio.remote_object_name)
        self.assertEqual(row.status, "uploaded")  # type: ignore[union-attr]
        evaluator._evaluation_service.upload_evaluation_file.assert_called_once()  # type: ignore[attr-defined]

    def test_upload_failed_row_with_changed_path_resets_before_retry(self):
        evaluator = self.make_evaluator()
        old_path = os.path.join(self.temp_dir.name, "old.wav")
        new_path = os.path.join(self.temp_dir.name, "new.wav")
        with open(old_path, "wb") as f:
            f.write(b"old audio")
        with open(new_path, "wb") as f:
            f.write(b"new audio")

        audio = FakeAudio(new_path, "stale-upload-failed.wav")
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.upsert_queued_file(
            evaluator.get_evaluation_id(), audio.remote_object_name, old_path
        )
        old_md5, old_size = calculate_file_md5_base64(old_path)
        evaluator._upload_ledger.mark_md5_ready(
            evaluator.get_evaluation_id(),
            audio.remote_object_name,
            old_md5,
            old_size,
        )
        evaluator._upload_ledger.mark_upload_failed(
            evaluator.get_evaluation_id(),
            audio.remote_object_name,
            "RuntimeError",
            "first path failed",
        )

        self.assertFalse(evaluator._should_skip_upload(audio))  # type: ignore[arg-type]

        row = evaluator._upload_ledger.get(
            evaluator.get_evaluation_id(), audio.remote_object_name
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "queued")
        self.assertEqual(row.local_path, new_path)
        self.assertIsNone(row.content_md5)
        self.assertIsNone(row.file_size)

    def test_queued_row_with_changed_path_resets_before_retry(self):
        evaluator = self.make_evaluator()
        old_path = os.path.join(self.temp_dir.name, "old-queued.wav")
        new_path = os.path.join(self.temp_dir.name, "new-queued.wav")
        with open(old_path, "wb") as f:
            f.write(b"old audio")
        with open(new_path, "wb") as f:
            f.write(b"new audio")

        audio = FakeAudio(new_path, "stale-queued.wav")
        assert evaluator._upload_ledger is not None
        evaluator._upload_ledger.upsert_queued_file(
            evaluator.get_evaluation_id(),
            audio.remote_object_name,
            old_path,
            file_index=0,
        )

        self.assertFalse(evaluator._should_skip_upload(audio))  # type: ignore[arg-type]

        row = evaluator._upload_ledger.get(
            evaluator.get_evaluation_id(), audio.remote_object_name
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "queued")
        self.assertEqual(row.local_path, new_path)

    def single_stimulus_groups(self, audios: List[FakeAudio]) -> List[FakeGroup]:
        """One group per file, mirroring real NMOS/QMOS single-stimulus layout."""
        return [FakeGroup(audios=[audio]) for audio in audios]

    def _ack_row(self, evaluator: Evaluator, remote: str) -> None:
        """Drive a seeded metadata_registered row through the real setter so its
        monotonic metadata_acked flag is set (seed_rows inserts default 0)."""
        evaluator._upload_ledger.mark_metadata_registered(  # type: ignore[union-attr]
            evaluator.get_evaluation_id(), remote
        )

    # ---- US-004 / c2 guard + c1 skip ----

    def test_metadata_acked_row_is_never_reregistered(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="acked")
        self.seed_rows(evaluator, audios, "metadata_registered")
        ledger = evaluator._upload_ledger
        e = evaluator.get_evaluation_id()
        r = audios[0].remote_object_name
        self._ack_row(evaluator, r)  # metadata_acked = 1
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)
        # churn metadata_registered -> verify_failed -> uploaded; ack must persist
        ledger.mark_verify_failed(e, r, "VERIFY_FAILED", "bad")  # type: ignore[union-attr]
        ledger.mark_md5_ready(e, r, content_md5, file_size)  # type: ignore[union-attr]
        ledger.mark_uploaded(e, r, "t0", "t1")  # type: ignore[union-attr]
        self.assertEqual(ledger.get(e, r).status, "uploaded")  # type: ignore[union-attr]
        self.assertTrue(ledger.get(e, r).metadata_acked)  # type: ignore[union-attr]

        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]
        evaluator._register_metadata_for_audios(audios)  # type: ignore[arg-type]

        service.create_evaluation_files.assert_not_called()

    def test_c2_guard_logs_skip_count(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="logskip")
        self.seed_rows(evaluator, audios, "metadata_registered")
        self._ack_row(evaluator, audios[0].remote_object_name)
        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]

        with self.assertLogs(level="INFO") as cm:
            evaluator._register_metadata_for_audios(audios)  # type: ignore[arg-type]

        self.assertTrue(
            any("Skipped metadata registration for 1" in line for line in cm.output)
        )
        service.create_evaluation_files.assert_not_called()

    def test_reverify_after_verify_failure_does_not_reregister(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="reverify")
        self.seed_rows(evaluator, audios, "metadata_registered")
        e = evaluator.get_evaluation_id()
        r = audios[0].remote_object_name
        self._ack_row(evaluator, r)  # acked
        evaluator._upload_ledger.mark_verify_failed(e, r, "VERIFY_FAILED", "bad")  # type: ignore[union-attr]

        service = Mock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        with patch("podonos.core.evaluator.UploadManager") as mock_manager_cls:
            mock_manager = Mock()
            mock_manager_cls.return_value = mock_manager
            evaluator._retry_failed_uploads(audios)  # type: ignore[arg-type]

        # re-uploaded but NOT re-registered (c1 skip + c2 guard)
        mock_manager.add_file_to_queue.assert_called_once()
        service.create_evaluation_files.assert_not_called()

    # ---- US-002 / c4 ordinal + manifest stability + merge gate ----

    def test_single_stimulus_groups_get_distinct_ordinals(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(4, prefix="single")
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]
        e = evaluator.get_evaluation_id()

        keys = [evaluator._idempotency_key(a) for a in audios]  # type: ignore[arg-type]
        self.assertEqual(keys, [f"{e}:{i}:0" for i in range(4)])
        self.assertEqual(len(set(keys)), 4)  # no collision -> no under-count
        ordinals = [evaluator._resolve_group_ordinal(a) for a in audios]  # type: ignore[arg-type]
        self.assertEqual(ordinals, [0, 1, 2, 3])

    def test_group_ordinal_shared_between_manifest_and_idempotency_key(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(3, prefix="shared")
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]
        for ordinal, audio in enumerate(audios):
            key = evaluator._idempotency_key(audio)  # type: ignore[arg-type]
            self.assertTrue(key.endswith(f":{ordinal}:0"))
            # the same persisted scalar feeds the manifest contract (G1)
            self.assertEqual(getattr(audio, "_podonos_group_ordinal"), ordinal)

    def test_queue_time_key_equals_md5_ready_persisted_key(self):
        evaluator = self.make_evaluator()
        evaluator._evaluation_service.get_presigned_url = MagicMock(  # type: ignore[method-assign]
            return_value="https://example.com/presigned-url"
        )
        evaluator._evaluation_service.upload_evaluation_file = MagicMock(  # type: ignore[method-assign]
            return_value=MagicMock()
        )
        evaluator.add_file(File(path=TESTDATA_SPEECH_CH1_MP3, model_tag="model"))
        evaluator._wait_for_uploads()

        ledger = evaluator._upload_ledger
        rows = ledger.list_by_status(evaluator.get_evaluation_id(), "uploaded")  # type: ignore[union-attr]
        self.assertEqual(len(rows), 1)
        audio = evaluator._ordered_file_groups[0].audios[0]
        # The key the md5-ready site persisted must equal the queue-time key for the
        # same audio (catches the upload_manager overwrite-no-op regression).
        self.assertIsNotNone(rows[0].manifest_key)
        self.assertEqual(rows[0].manifest_key, evaluator._build_current_manifest_key(audio))

    def test_merge_gate_rejects_reordered_acked_row_but_not_same_order(self):
        evaluator = self.make_evaluator()
        ledger = evaluator._upload_ledger
        e = evaluator.get_evaluation_id()
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)

        def make_audio(remote: str, group_id: str) -> Audio:
            audio = Audio(
                path=TESTDATA_SPEECH_CH1_MP3,
                name="speech_ch1.mp3",
                remote_object_name=remote,
                script="s",
                tags=["t"],
                model_tag="m",
                is_ref=False,
                group=group_id,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            audio.set_integrity_info(content_md5, file_size)
            return audio

        orig = make_audio("slot.wav", "random-group-A")
        setattr(orig, "_podonos_group_ordinal", 0)
        hash0 = build_upload_manifest_hash(
            stable_manifest_contract(orig.to_create_file_dict(), 0),
            content_md5,
            file_size,
        )
        ledger.upsert_queued_file(e, "slot.wav", orig.path)  # type: ignore[union-attr]
        ledger.mark_md5_ready(e, "slot.wav", content_md5, file_size, manifest_hash=hash0)  # type: ignore[union-attr]
        ledger.mark_uploaded(e, "slot.wav", "t0", "t1")  # type: ignore[union-attr]
        ledger.mark_metadata_registered(e, "slot.wav")  # type: ignore[union-attr] # acked
        ledger.mark_verified(e, "slot.wav")  # type: ignore[union-attr]

        # same-order resume: regenerated group_id but SAME ordinal -> hash matches ->
        # no false-positive raise, skips as verified.
        same = make_audio("slot.wav", "random-group-B")
        setattr(same, "_podonos_group_ordinal", 0)
        response = evaluator._verify_files_in_batches(e, [same])  # type: ignore[arg-type]
        self.assertTrue(response.all_verified)

        # reordered resume: byte-identical file, DIFFERENT ordinal -> hash differs ->
        # loud ValueError instead of a silent duplicate.
        reordered = make_audio("slot.wav", "random-group-C")
        setattr(reordered, "_podonos_group_ordinal", 1)
        with self.assertRaises(ValueError):
            evaluator._verify_files_in_batches(e, [reordered])  # type: ignore[arg-type]

    # ---- US-003 / c3 idempotency key ----

    def test_idempotency_keys_aligned_to_batch_to_register(self):
        # N1: keys are built in lockstep with the post-guard register list, so an
        # acked (skipped) row does not shift the remaining keys onto wrong files.
        evaluator = self.make_evaluator()
        audios = self.fake_audios(3, prefix="align")
        self.seed_rows(evaluator, audios, "uploaded")
        # ack the MIDDLE row so it is skipped by the guard
        self._ack_row(evaluator, audios[1].remote_object_name)
        service = MagicMock()
        evaluator._evaluation_service = service  # type: ignore[assignment]
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]

        evaluator._register_metadata_for_audios(audios)  # type: ignore[arg-type]

        call = service.create_evaluation_files.call_args
        registered = call.args[1]
        keys = call.kwargs["idempotency_keys"]
        e = evaluator.get_evaluation_id()
        # row 1 skipped; the surviving rows keep their OWN ordinals (0 and 2)
        self.assertEqual(
            [a.remote_object_name for a in registered],
            [audios[0].remote_object_name, audios[2].remote_object_name],
        )
        self.assertEqual(keys, [f"{e}:0:0", f"{e}:2:0"])
        self.assertEqual(len(keys), len(registered))

    def test_build_create_files_body_zips_keys_and_validates_length(self):
        audios = self.fake_audios(2, prefix="body")
        body = EvaluationService._build_create_files_body(audios, ["k0", "k1"])
        self.assertEqual([f["idempotency_key"] for f in body], ["k0", "k1"])
        self.assertEqual(body[0]["uploaded_file_name"], audios[0].remote_object_name)
        # None -> no idempotency_key field (OQ2 backward-compatible path)
        plain = EvaluationService._build_create_files_body(audios, None)
        self.assertNotIn("idempotency_key", plain[0])
        with self.assertRaises(ValueError):
            EvaluationService._build_create_files_body(audios, ["only-one"])

    def test_e2e_verify_failure_yields_exactly_one_row_per_slot(self):
        evaluator = self.make_evaluator()
        audios = self.fake_audios(5, prefix="e2e")
        self.seed_rows(evaluator, audios, "uploaded")
        evaluator._ordered_file_groups = self.single_stimulus_groups(audios)  # type: ignore[assignment]
        e = evaluator.get_evaluation_id()

        registered_keys: List[str] = []

        def create_files(evaluation_id, batch, **kwargs):
            registered_keys.extend(kwargs.get("idempotency_keys") or [])

        failed_once = {"done": False}

        def verify_files(evaluation_id, batch, **kwargs):
            results = []
            for audio in batch:
                if (
                    audio.remote_object_name == audios[2].remote_object_name
                    and not failed_once["done"]
                ):
                    results.append(
                        FileVerificationResult(
                            audio.remote_object_name,
                            False,
                            None,
                            VerificationErrorDetail(
                                code="SIZE_MISMATCH",
                                message="bad",
                                expected="1",
                                actual="0",
                            ),
                        )
                    )
                else:
                    results.append(
                        FileVerificationResult(audio.remote_object_name, True, "m", None)
                    )
            failed = sum(1 for r in results if not r.verified)
            if failed:
                failed_once["done"] = True
            return VerifyFilesResponse(
                all_verified=(failed == 0),
                verified_count=len(results) - failed,
                failed_count=failed,
                results=results,
            )

        service = evaluator._evaluation_service  # real EvaluationService instance
        service.process_files = MagicMock(return_value=SimpleNamespace(processing_count=0))  # type: ignore[method-assign]
        service.create_evaluation_files = MagicMock(side_effect=create_files)  # type: ignore[method-assign]
        service.verify_files = MagicMock(side_effect=verify_files)  # type: ignore[method-assign]
        service.get_presigned_url = MagicMock(return_value="https://example.com/x")  # type: ignore[method-assign]
        service.upload_evaluation_file = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]

        evaluator._process_audio_files_with_verification()

        # exactly one registration per slot; the re-verified slot was NOT re-POSTed
        self.assertEqual(len(registered_keys), 5)
        self.assertEqual(set(registered_keys), {f"{e}:{i}:0" for i in range(5)})
        self.assertEqual(registered_keys.count(f"{e}:2:0"), 1)
        self.assertEqual(
            evaluator._upload_ledger.counts_by_status(e)["verified"],  # type: ignore[union-attr]
            5,
        )

    def test_should_skip_upload_fails_closed_on_acked_row_with_changed_metadata(self):
        # An already-acked row whose per-file metadata changed must fail loudly, not
        # silently reset+skip (which would leave stale metadata at the backend).
        evaluator = self.make_evaluator()
        ledger = evaluator._upload_ledger
        e = evaluator.get_evaluation_id()
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)

        def make_audio(script: str) -> Audio:
            audio = Audio(
                path=TESTDATA_SPEECH_CH1_MP3,
                name="speech_ch1.mp3",
                remote_object_name="slot.wav",
                script=script,
                tags=["t"],
                model_tag="m",
                is_ref=False,
                group=None,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            audio.set_integrity_info(content_md5, file_size)
            return audio

        original = make_audio("original-script")
        hash0 = build_upload_manifest_hash(
            stable_manifest_contract(original.to_create_file_dict(), None),
            content_md5,
            file_size,
        )
        ledger.upsert_queued_file(e, "slot.wav", original.path, file_index=0)  # type: ignore[union-attr]
        ledger.mark_md5_ready(e, "slot.wav", content_md5, file_size, manifest_hash=hash0)  # type: ignore[union-attr]
        ledger.mark_uploaded(e, "slot.wav", "t0", "t1")  # type: ignore[union-attr]
        ledger.mark_metadata_registered(e, "slot.wav")  # acked
        ledger.mark_verify_failed(e, "slot.wav", "VERIFY_FAILED", "bad")  # type: ignore[union-attr]

        changed = make_audio("CHANGED-script")
        with self.assertRaises(ValueError):
            evaluator._should_skip_upload(changed)  # type: ignore[arg-type]
        # the row was NOT reset for re-upload (would have stranded stale metadata)
        row = ledger.get(e, "slot.wav")  # type: ignore[union-attr]
        self.assertEqual(row.status, "verify_failed")
        self.assertTrue(row.metadata_acked)

    def test_resume_routes_uploaded_acked_row_back_to_verification(self):
        # c1 crash window: an acked row was re-uploaded (status uploaded) but the
        # process died before the in-run re-verify. On resume it must be routed to
        # verification (the c2 guard skips its registration), not finalized unverified.
        evaluator = self.make_evaluator()
        audios = self.fake_audios(1, prefix="crashwindow")
        self.seed_rows(evaluator, audios, "metadata_registered")
        e = evaluator.get_evaluation_id()
        r = audios[0].remote_object_name
        self._ack_row(evaluator, r)
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)
        evaluator._upload_ledger.mark_verify_failed(e, r, "V", "bad")  # type: ignore[union-attr]
        evaluator._upload_ledger.mark_md5_ready(e, r, content_md5, file_size)  # type: ignore[union-attr]
        evaluator._upload_ledger.mark_uploaded(e, r, "t0", "t1")  # type: ignore[union-attr]
        row = evaluator._upload_ledger.get(e, r)  # type: ignore[union-attr]
        self.assertEqual(row.status, "uploaded")
        self.assertTrue(row.metadata_acked)

        needing = evaluator._get_audios_needing_verification(audios)  # type: ignore[arg-type]
        self.assertEqual([a.remote_object_name for a in needing], [r])

    def test_idempotency_key_unresolved_ordinal_is_distinct_per_file(self):
        evaluator = self.make_evaluator()
        a = self.fake_audios(1, prefix="alpha")[0]
        b = self.fake_audios(1, prefix="beta")[0]
        # neither audio belongs to a group -> unresolved ordinal -> the keys must
        # still be distinct (a `:0:` collapse would make the backend merge slots)
        key_a = evaluator._idempotency_key(a)  # type: ignore[arg-type]
        key_b = evaluator._idempotency_key(b)  # type: ignore[arg-type]
        self.assertNotEqual(key_a, key_b)
        self.assertIn(a.remote_object_name, key_a)

    def test_comparison_group_manifest_stable_across_group_id_regen(self):
        # Real-Audio coverage of the production ordinal-substitution path for a
        # non-None (comparison) group: a regenerated random group_id with the same
        # positional ordinal yields the same manifest key; a different ordinal does not.
        evaluator = self.make_evaluator()
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)

        def make_audio(remote: str, group_id: str, ordinal: int) -> Audio:
            audio = Audio(
                path=TESTDATA_SPEECH_CH1_MP3,
                name="speech_ch1.mp3",
                remote_object_name=remote,
                script="s",
                tags=["t"],
                model_tag="m",
                is_ref=False,
                group=group_id,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            audio.set_integrity_info(content_md5, file_size)
            setattr(audio, "_podonos_group_ordinal", ordinal)
            return audio

        run1 = make_audio("r1.wav", "1700000000000_uuid-A", 0)
        run2 = make_audio("r2.wav", "1700000001111_uuid-B", 0)
        self.assertEqual(
            evaluator._build_current_manifest_key(run1),  # type: ignore[arg-type]
            evaluator._build_current_manifest_key(run2),  # type: ignore[arg-type]
        )
        other_group = make_audio("r3.wav", "1700000000000_uuid-A", 1)
        self.assertNotEqual(
            evaluator._build_current_manifest_key(run1),  # type: ignore[arg-type]
            evaluator._build_current_manifest_key(other_group),  # type: ignore[arg-type]
        )

    def test_process_finalization_hash_stable_across_comparison_group_id_regen(self):
        # The process-files dedupe hash must not flip when a comparison group's
        # random group_id is regenerated on a cross-process resume (else is_processed
        # misses and process_files needlessly re-runs). Single-stimulus group=None
        # must keep the legacy raw hash for backward compatibility.
        evaluator = self.make_evaluator()
        content_md5, file_size = calculate_file_md5_base64(TESTDATA_SPEECH_CH1_MP3)

        def mk(group_id, ordinal):
            audio = Audio(
                path=TESTDATA_SPEECH_CH1_MP3,
                name="speech_ch1.mp3",
                remote_object_name="slot.wav",  # rebound from ledger on resume -> stable
                script="s",
                tags=["t"],
                model_tag="m",
                is_ref=False,
                group=group_id,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            audio.set_integrity_info(content_md5, file_size)
            setattr(audio, "_podonos_group_ordinal", ordinal)
            return audio

        def proc_hash(audio):
            return evaluator._finalization_hash(  # type: ignore[attr-defined]
                {
                    "evaluation_id": evaluator.get_evaluation_id(),
                    "files": [evaluator._stable_manifest_contract(audio)],  # type: ignore[attr-defined]
                }
            )

        # comparison group: regenerated random group_id, same ordinal -> same hash
        self.assertEqual(proc_hash(mk("rand-A", 0)), proc_hash(mk("rand-B", 0)))
        # the fix is load-bearing: raw to_create_file_dict would differ
        raw_a = evaluator._finalization_hash(  # type: ignore[attr-defined]
            {"evaluation_id": evaluator.get_evaluation_id(), "files": [mk("rand-A", 0).to_create_file_dict()]}
        )
        raw_b = evaluator._finalization_hash(  # type: ignore[attr-defined]
            {"evaluation_id": evaluator.get_evaluation_id(), "files": [mk("rand-B", 0).to_create_file_dict()]}
        )
        self.assertNotEqual(raw_a, raw_b)
        # single-stimulus (group=None) keeps the legacy raw hash (backward compatible)
        single = mk(None, 0)
        self.assertEqual(
            proc_hash(single),
            evaluator._finalization_hash(  # type: ignore[attr-defined]
                {"evaluation_id": evaluator.get_evaluation_id(), "files": [single.to_create_file_dict()]}
            ),
        )

    def test_default_evaluator_does_not_create_state_file(self):
        evaluator = self.make_evaluator(resume_upload=False)

        self.assertIsNone(evaluator._upload_ledger)  # type: ignore[attr-defined]
        self.assertFalse(os.path.exists(self.state_path))


if __name__ == "__main__":
    unittest.main()
