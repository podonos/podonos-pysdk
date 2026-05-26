import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List
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
)
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

    def to_create_file_dict(self):
        return {"uploaded_file_name": self.remote_object_name, "original_name": self.path}

    def set_integrity_info(self, content_md5: str, file_size: int) -> None:
        self.content_md5 = content_md5
        self.file_size = file_size

    def set_upload_at(self, start_at: str, finish_at: str) -> None:
        self.upload_start_at = start_at
        self.upload_finish_at = finish_at


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

    def test_default_evaluator_does_not_create_state_file(self):
        evaluator = self.make_evaluator(resume_upload=False)

        self.assertIsNone(evaluator._upload_ledger)  # type: ignore[attr-defined]
        self.assertFalse(os.path.exists(self.state_path))


if __name__ == "__main__":
    unittest.main()
