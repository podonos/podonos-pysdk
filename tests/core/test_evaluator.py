import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import List
from unittest.mock import Mock, patch
from uuid import uuid4

from glog import FailedCheckException  # type: ignore

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluator import Evaluator
from podonos.core.file import Audio, AudioGroup, File
from podonos.core.upload_ledger import UploadLedger
from podonos.entity.evaluation import EvaluationEntity
from podonos.entity.verification import FileVerificationResult, VerifyFilesResponse
from podonos.errors import InvalidFileError
from tests.core.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV


class TestEvaluator(unittest.TestCase):
    def setUp(self):
        # Mock API client
        self.api_client = Mock(spec=APIClient)

        # Create mock evaluation
        current_time = datetime.now(timezone.utc)
        self.mock_evaluation = EvaluationEntity(
            id="test_id",
            title="test_title",
            internal_name=None,
            description=None,
            batch_size=1,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )

        # Patch _set_evaluation before initialization
        with patch.object(
            Evaluator, "_set_evaluation", return_value=self.mock_evaluation
        ):
            self.eval_config = EvalConfig(type=EvalType.NMOS.value)
            self.evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=self.eval_config,
                supported_eval_types=[EvalType.NMOS],
            )

        self.test_wav = TESTDATA_SPEECH_TWO_CH1_WAV

    def test_should_initialize_evaluator_successfully(self):
        # Given
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        # When
        with patch.object(
            Evaluator, "_set_evaluation", return_value=self.mock_evaluation
        ):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.NMOS],
            )

        # Then
        self.assertEqual(evaluator._eval_config, eval_config)  # type: ignore
        self.assertTrue(evaluator._initialized)  # type: ignore
        self.assertEqual(evaluator._ordered_file_groups, [])  # type: ignore

    def test_upload_ledger_contract_mismatch_error_omits_raw_values(self):
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            "test_id",
            {
                "evaluation_id": "test_id",
                "eval_type": EvalType.NMOS.value,
                "eval_language": "en-us",
                "eval_batch_size": 1,
                "eval_template_id": None,
                "use_annotation": False,
                "use_loudness_normalization": True,
                "session_config": {
                    "eval_name": "customer pii name",
                    "eval_description": "password=SECRET",
                },
            },
        )
        eval_config = EvalConfig(
            name="different-name",
            desc="different-description",
            type=EvalType.NMOS.value,
            resume_upload=True,
            upload_state_path=state_path,
        )

        with self.assertRaises(ValueError) as context:
            with patch.object(
                Evaluator, "_set_evaluation", return_value=self.mock_evaluation
            ):
                Evaluator(
                    api_client=self.api_client,
                    eval_config=eval_config,
                    supported_eval_types=[EvalType.NMOS],
                )

        message = str(context.exception)
        self.assertIn("mismatched keys", message)
        self.assertIn("session_config", message)
        self.assertNotIn("customer pii name", message)
        self.assertNotIn("password=SECRET", message)
        self.assertNotIn("different-description", message)

    def test_should_create_evaluation_successfully(self):
        # Given
        current_time = datetime.now(timezone.utc)
        mock_response = {
            "id": "test_id",
            "title": "test_title",
            "internal_name": None,
            "description": None,
            "batch_size": 1,
            "status": "DRAFT",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.api_client.post.return_value = Mock(
            status_code=200, json=lambda: mock_response
        )

        # When
        evaluation = self.evaluator._set_evaluation(self.eval_config)  # type: ignore

        # Then
        self.assertIsInstance(evaluation, EvaluationEntity)
        self.assertEqual(evaluation.id, "test_id")
        self.assertEqual(evaluation.status, "DRAFT")

    def test_should_create_evaluation_from_template_successfully(self):
        # Given
        current_time = datetime.now(timezone.utc)
        mock_response = {
            "id": "test_id",
            "title": "test_title",
            "internal_name": None,
            "description": None,
            "batch_size": 1,
            "status": "DRAFT",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.api_client.post.return_value = Mock(
            status_code=200, json=lambda: mock_response
        )
        self.eval_config._eval_template_id = "test_template_id"  # type: ignore

        # When
        evaluation = self.evaluator._set_evaluation(self.eval_config)  # type: ignore

        # Then
        self.assertIsInstance(evaluation, EvaluationEntity)
        self.assertEqual(evaluation.id, "test_id")
        self.assertEqual(evaluation.status, "DRAFT")

    def test_should_validate_eval_type_successfully(self):
        # Test single file evaluation types
        assert self.evaluator._eval_config is not None  # type: ignore
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        self.evaluator._validate_eval_type("add_file")  # type: ignore

        # Test comparison evaluation types
        self.evaluator._eval_config._eval_type = EvalType.CMOS  # type: ignore
        self.evaluator._validate_eval_type("add_files")  # type: ignore

    def test_should_validate_eval_type_raise_error(self):
        # Given
        self.evaluator._eval_config._eval_type = EvalType.CMOS  # type: ignore

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_eval_type("add_file")  # type: ignore
        self.assertIn(
            "The 'add_file' is only supported for single file evaluation types:",
            str(context.exception),
        )

    def test_add_file_should_not_queue_upload_when_audio_validation_fails(self):
        # Given
        file = File(path=self.test_wav, model_tag="test_model")

        # When/Then
        with patch(
            "podonos.core.file.AudioMeta",
            side_effect=InvalidFileError("late decode failure"),
        ), patch.object(self.evaluator, "_upload_one_file") as mock_upload:
            with self.assertRaises(InvalidFileError):
                self.evaluator.add_file(file)

            mock_upload.assert_not_called()

    def test_should_cleanup_successfully(self):
        # Given
        self.evaluator._initialized = True  # type: ignore
        self.evaluator._ordered_file_groups = [
            AudioGroup(group_id="group1", audios=[], created_at=datetime.now())
        ]  # type: ignore

        # When
        self.evaluator._cleanup()  # type: ignore

        # Then
        self.assertFalse(self.evaluator._initialized)  # type: ignore
        self.assertEqual(self.evaluator._ordered_file_groups, [])  # type: ignore

    @patch("podonos.service.evaluation_service.EvaluationService.upload_session_json")
    def test_should_upload_session_json_successfully(self, mock_upload: Mock):
        # Given
        self.evaluator._evaluation = Mock(id="test_eval_id")  # type: ignore
        self.evaluator._evaluation_service = Mock()  # type: ignore

        # When
        self.evaluator._upload_session_json()  # type: ignore

        # Then
        self.evaluator._evaluation_service.upload_session_json.assert_called_once_with(  # type: ignore
            self.evaluator._evaluation.id,
            self.evaluator._eval_config,
            self.evaluator._ordered_file_groups,  # type: ignore
        )

    def test_should_update_audio_upload_times(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="test.wav",
            script=None,
            tags=[],
            model_tag="test_model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        upload_start = {"test.wav": "2024-01-01T00:00:00Z"}
        upload_finish = {"test.wav": "2024-01-01T00:01:00Z"}

        # When
        self.evaluator._update_audio_upload_times(audio, upload_start, upload_finish)  # type: ignore

        # Then
        self.assertEqual(getattr(audio, "_upload_start_at"), upload_start["test.wav"])  # type: ignore
        self.assertEqual(getattr(audio, "_upload_finish_at"), upload_finish["test.wav"])  # type: ignore

    def test_should_process_upload_times(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote/test.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group="test_group",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        group = AudioGroup(
            group_id="test_group", audios=[audio], created_at=datetime.now()
        )
        self.evaluator._ordered_file_groups = [group]  # type: ignore
        self.evaluator._upload_manager = Mock()  # type: ignore
        upload_start = {"remote/test.wav": "2024-01-01T00:00:00Z"}
        upload_finish = {"remote/test.wav": "2024-01-01T00:01:00Z"}
        self.evaluator._upload_manager.get_upload_time.return_value = (
            upload_start,
            upload_finish,
        )  # type: ignore

        # When
        self.evaluator._process_upload_times()  # type: ignore

        # Then
        self.assertEqual(audio._upload_start_at, upload_start["remote/test.wav"])  # type: ignore
        self.assertEqual(audio._upload_finish_at, upload_finish["remote/test.wav"])  # type: ignore

    def test_should_validate_close(self):
        # Given
        self.evaluator._initialized = True  # type: ignore
        self.evaluator._upload_manager = Mock()  # type: ignore

        # When/Then
        self.evaluator._validate_close()  # type: ignore

    def test_should_validate_close_raise_error(self):
        # Given
        self.evaluator._initialized = False  # type: ignore

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_close()  # type: ignore
        self.assertEqual(str(context.exception), "No evaluation session is open.")

    def test_get_evaluation_id_successfully(self):
        """Test get_evaluation_id returns correct ID"""
        # Given
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # When
        eval_id = self.evaluator.get_evaluation_id()

        # Then
        self.assertEqual(eval_id, "test_id")

    def test_get_evaluation_id_raises_error_when_not_initialized(self):
        """Test get_evaluation_id raises error when evaluation is None"""
        # Given
        self.evaluator._evaluation = None  # type: ignore

        # When/Then
        with self.assertRaises(AssertionError):
            self.evaluator.get_evaluation_id()

    def test_validate_initialization_with_invalid_api_client(self):
        """Test _validate_initialization raises error for invalid api_client"""
        # Given
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        # When/Then
        with self.assertRaises(FailedCheckException):
            self.evaluator._validate_initialization(None, eval_config, [EvalType.NMOS])  # type: ignore

    def test_validate_initialization_with_invalid_eval_config(self):
        """Test _validate_initialization raises error for invalid eval_config"""
        # When/Then
        with self.assertRaises(FailedCheckException):
            self.evaluator._validate_initialization(
                self.api_client, None, [EvalType.NMOS]
            )  # type: ignore

    def test_validate_initialization_with_unsupported_eval_type(self):
        """Test _validate_initialization raises error for unsupported eval type"""
        # Given
        eval_config = EvalConfig(type=EvalType.PREF.value)

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_initialization(
                self.api_client, eval_config, [EvalType.NMOS]
            )  # type: ignore
        self.assertIn("Not supported evaluation type", str(context.exception))

    def test_initialize_attributes_sets_all_attributes(self):
        """Test _initialize_attributes properly sets all class attributes"""
        # Given
        eval_config = EvalConfig(type=EvalType.NMOS.value)
        evaluator = object.__new__(Evaluator)  # Create uninitialized instance

        # When
        with patch.object(
            Evaluator, "_set_evaluation", return_value=self.mock_evaluation
        ):
            evaluator._initialize_attributes(
                self.api_client, eval_config, [EvalType.NMOS]
            )  # type: ignore

        # Then
        self.assertEqual(evaluator._api_client, self.api_client)  # type: ignore
        self.assertEqual(evaluator._eval_config, eval_config)  # type: ignore
        self.assertIsNotNone(evaluator._evaluation_service)  # type: ignore
        self.assertIsNotNone(evaluator._file_transformer)  # type: ignore
        self.assertIsNotNone(evaluator._file_validator)  # type: ignore
        self.assertEqual(evaluator._supported_eval_types, [EvalType.NMOS])  # type: ignore
        self.assertEqual(evaluator._ordered_file_groups, [])  # type: ignore
        self.assertIsNone(evaluator._upload_manager)  # type: ignore

    def test_validate_eval_type_for_ranking(self):
        """Test _validate_eval_type for add_ranking_set"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore

        # When/Then (should not raise)
        self.evaluator._validate_eval_type("add_ranking_set")  # type: ignore

    def test_validate_eval_type_raises_for_wrong_ranking_type(self):
        """Test _validate_eval_type raises error when using add_ranking_set with non-RANKING type"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_eval_type("add_ranking_set")  # type: ignore
        self.assertIn("add_ranking_set", str(context.exception))
        self.assertIn("ranking evaluation types", str(context.exception))

    @patch("podonos.core.evaluator.UploadManager")
    def test_upload_one_file_initializes_upload_manager_lazily(
        self, mock_upload_manager: Mock
    ):
        # Given
        self.evaluator._upload_manager = None  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        mock_instance = Mock()
        mock_upload_manager.return_value = mock_instance

        test_audio = Audio(
            path=self.test_wav,
            name="test.wav",
            remote_object_name="remote_name",
            script=None,
            tags=[],
            model_tag="test_model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        self.evaluator._upload_one_file("eval_id", test_audio)  # type: ignore

        # Then
        mock_upload_manager.assert_called_once()
        mock_instance.add_file_to_queue.assert_called_once_with("eval_id", test_audio)

    def test_upload_one_file_raises_error_when_no_eval_config(self):
        # Given
        self.evaluator._eval_config = None  # type: ignore

        test_audio = Audio(
            path=self.test_wav,
            name="test.wav",
            remote_object_name="remote_name",
            script=None,
            tags=[],
            model_tag="test_model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._upload_one_file("eval_id", test_audio)  # type: ignore
        self.assertIn("No evaluation session is open", str(context.exception))

    def test_upload_one_file_uses_existing_upload_manager(self):
        # Given
        mock_upload_manager = Mock()
        self.evaluator._upload_manager = mock_upload_manager  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        test_audio = Audio(
            path=self.test_wav,
            name="test.wav",
            remote_object_name="remote_name",
            script=None,
            tags=[],
            model_tag="test_model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        self.evaluator._upload_one_file("eval_id", test_audio)  # type: ignore

        # Then
        mock_upload_manager.add_file_to_queue.assert_called_once_with(
            "eval_id", test_audio
        )

    def _create_test_audio(self, index: int) -> Audio:
        """Helper method to create test Audio objects."""
        audio = Audio(
            path=self.test_wav,
            name=f"test{index}.wav",
            remote_object_name=f"remote/test{index}.wav",
            script=None,
            tags=[],
            model_tag="test_model",
            is_ref=False,
            group=f"group{index}",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)
        return audio

    def _create_mock_verify_response(
        self,
        audios: List[Audio],
        all_verified: bool = True,
        failed_indices: List[int] = None,
    ) -> VerifyFilesResponse:
        """Helper method to create mock VerifyFilesResponse."""
        failed_indices = failed_indices or []
        results = []
        verified_count = 0
        failed_count = 0

        for i, audio in enumerate(audios):
            is_verified = i not in failed_indices
            results.append(
                FileVerificationResult(
                    uploaded_file_name=audio.remote_object_name,
                    verified=is_verified,
                    file_meta_id=f"meta_{i}" if is_verified else None,
                    error=None,
                )
            )
            if is_verified:
                verified_count += 1
            else:
                failed_count += 1

        return VerifyFilesResponse(
            all_verified=all_verified and failed_count == 0,
            verified_count=verified_count,
            failed_count=failed_count,
            results=results,
        )

    def test_process_audio_files_with_verification_batches_correctly(self):
        # Given
        groups: List[AudioGroup] = []
        for i in range(600):
            audio = self._create_test_audio(i)
            group = AudioGroup(
                group_id=f"group{i}", audios=[audio], created_at=datetime.now()
            )
            groups.append(group)

        self.evaluator._ordered_file_groups = groups  # type: ignore
        mock_service = Mock()

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            return self._create_mock_verify_response(batch)

        mock_service.verify_files.side_effect = mock_verify_files
        mock_service.process_files.return_value = Mock(processing_count=600)
        self.evaluator._evaluation_service = mock_service  # type: ignore
        self.evaluator._upload_manager = None  # type: ignore

        # When
        self.evaluator._process_audio_files_with_verification()  # type: ignore

        # Then
        self.assertEqual(mock_service.create_evaluation_files.call_count, 2)
        for call in mock_service.create_evaluation_files.call_args_list:
            self.assertEqual(call.kwargs["timeout"], self.evaluator._eval_config.api_timeout)  # type: ignore
        # verify_files should be called 2 times (600 files / 100 batch size = 6 batches)
        self.assertEqual(mock_service.verify_files.call_count, 6)
        self.assertEqual(mock_service.process_files.call_args.kwargs["timeout"], self.evaluator._eval_config.api_timeout)  # type: ignore

    def test_verify_files_in_batches_single_batch(self):
        """Test _verify_files_in_batches with file count less than batch size."""
        # Given
        audios = [self._create_test_audio(i) for i in range(100)]
        mock_service = Mock()
        mock_response = self._create_mock_verify_response(audios)
        mock_service.verify_files.return_value = mock_response
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        mock_service.verify_files.assert_called_once()
        call = mock_service.verify_files.call_args
        self.assertEqual(call.args[0], "eval_id")
        self.assertEqual(call.args[1], audios)
        self.assertEqual(call.kwargs["timeout"], self.evaluator._eval_config.verify_timeout)  # type: ignore
        self.assertIn("batch_index", call.kwargs["context"])
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, 100)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), 100)

    def test_verify_files_in_batches_multiple_batches(self):
        """Test _verify_files_in_batches with file count exceeding batch size."""
        # Given
        total_files = 1200  # Should create 12 batches of 100 by default
        audios = [self._create_test_audio(i) for i in range(total_files)]
        mock_service = Mock()

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            return self._create_mock_verify_response(batch)

        mock_service.verify_files.side_effect = mock_verify_files
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        self.assertEqual(mock_service.verify_files.call_count, 12)

        # Verify batch sizes
        batch_size = self.evaluator._eval_config.verify_batch_size
        calls = mock_service.verify_files.call_args_list
        self.assertEqual(len(calls[0][0][1]), batch_size)
        self.assertEqual(len(calls[-1][0][1]), batch_size)

        # Verify aggregated results
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, total_files)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), total_files)

    def test_verify_files_in_batches_exact_batch_size(self):
        """Test _verify_files_in_batches with file count exactly equal to batch size."""
        # Given
        batch_size = self.evaluator._eval_config.verify_batch_size
        audios = [self._create_test_audio(i) for i in range(batch_size)]
        mock_service = Mock()
        mock_response = self._create_mock_verify_response(audios)
        mock_service.verify_files.return_value = mock_response
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        mock_service.verify_files.assert_called_once()
        self.assertEqual(result.verified_count, batch_size)

    def test_verify_files_in_batches_aggregates_failures_correctly(self):
        """Test _verify_files_in_batches correctly aggregates failed results."""
        # Given
        total_files = 1000  # 10 batches of 100 by default
        audios = [self._create_test_audio(i) for i in range(total_files)]
        mock_service = Mock()

        call_count = [0]

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            # First batch: 3 failures (indices 0, 10, 20)
            # Second batch: 2 failures (indices 0, 5)
            if call_count[0] == 0:
                failed_indices = [0, 10, 20]
            else:
                failed_indices = [0, 5]
            call_count[0] += 1
            return self._create_mock_verify_response(
                batch, all_verified=False, failed_indices=failed_indices
            )

        mock_service.verify_files.side_effect = mock_verify_files
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        self.assertFalse(result.all_verified)
        self.assertEqual(result.verified_count, 979)  # 1000 - 21 failures across 10 batches
        self.assertEqual(result.failed_count, 21)  # 3 from first batch + 2 from each remaining batch
        self.assertEqual(len(result.results), total_files)

        # Verify failed results are in the correct positions
        failed_results = [r for r in result.results if not r.verified]
        self.assertEqual(len(failed_results), 21)

    def test_verify_files_in_batches_empty_list(self):
        """Test _verify_files_in_batches with empty file list."""
        # Given
        audios: List[Audio] = []
        mock_service = Mock()
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        mock_service.verify_files.assert_not_called()
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, 0)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), 0)

    def test_retry_failed_uploads_reuploads_without_reregistering_metadata(self):
        """A verify-failure retry repairs the S3 object (re-upload) ONLY; it must not
        re-POST create_evaluation_files for a file that was already registered. On the
        default config (no upload ledger) this is the exactly-once guarantee that
        removes the duplicate-evaluation_file trigger."""
        failed_audio = self._create_test_audio(1)
        self.assertIsNone(self.evaluator._upload_ledger)  # type: ignore[attr-defined]
        mock_service = Mock()
        self.evaluator._evaluation_service = mock_service  # type: ignore

        with patch("podonos.core.evaluator.UploadManager") as mock_manager_cls:
            mock_manager = Mock()
            mock_manager_cls.return_value = mock_manager

            self.evaluator._retry_failed_uploads([failed_audio])  # type: ignore

        # re-uploaded (bytes repaired) ...
        mock_manager.add_file_to_queue.assert_called_once_with(
            self.evaluator.get_evaluation_id(), failed_audio
        )
        mock_manager.wait_and_close.assert_called_once()
        # ... but NOT re-registered (already registered in the main path)
        mock_service.create_evaluation_files.assert_not_called()

    def test_verify_files_in_batches_large_file_count(self):
        """Test _verify_files_in_batches with 1900 files (customer issue scenario)."""
        # Given
        total_files = 1900  # Customer's file count; default verify_batch_size=100 means 19 batches
        audios = [self._create_test_audio(i) for i in range(total_files)]
        mock_service = Mock()

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            return self._create_mock_verify_response(batch)

        mock_service.verify_files.side_effect = mock_verify_files
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = self.evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        batch_size = self.evaluator._eval_config.verify_batch_size
        expected_batches = (total_files + batch_size - 1) // batch_size
        self.assertEqual(
            mock_service.verify_files.call_count, expected_batches
        )
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, total_files)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), total_files)

    def test_process_audio_files_with_verification_uses_batched_verify(self):
        """Test _process_audio_files_with_verification uses batched verification."""
        # Given
        total_files = 1200
        groups: List[AudioGroup] = []
        for i in range(total_files):
            audio = self._create_test_audio(i)
            group = AudioGroup(
                group_id=f"group{i}", audios=[audio], created_at=datetime.now()
            )
            groups.append(group)

        self.evaluator._ordered_file_groups = groups  # type: ignore
        mock_service = Mock()

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            return self._create_mock_verify_response(batch)

        mock_service.verify_files.side_effect = mock_verify_files
        mock_service.process_files.return_value = Mock(processing_count=total_files)
        self.evaluator._evaluation_service = mock_service  # type: ignore

        # When
        self.evaluator._process_audio_files_with_verification()  # type: ignore

        # Then
        # verify_files should use the configured 100-file default batch size
        self.assertEqual(mock_service.verify_files.call_count, 12)
        # create_evaluation_files should also be batched
        self.assertEqual(mock_service.create_evaluation_files.call_count, 3)

    def test_process_upload_times_handles_no_upload_manager(self):
        """Test _process_upload_times handles case when upload_manager is None"""
        # Given
        self.evaluator._upload_manager = None  # type: ignore
        self.evaluator._ordered_file_groups = []  # type: ignore

        # When/Then (should not raise)
        self.evaluator._process_upload_times()  # type: ignore

    def test_wait_for_uploads_calls_upload_manager(self):
        """Test _wait_for_uploads calls wait_and_close on upload_manager"""
        # Given
        mock_upload_manager = Mock()
        mock_upload_manager.wait_and_close.return_value = True
        self.evaluator._upload_manager = mock_upload_manager  # type: ignore

        # When
        self.evaluator._wait_for_uploads()  # type: ignore

        # Then
        mock_upload_manager.wait_and_close.assert_called_once()

    @patch.object(Evaluator, "_wait_for_uploads")
    @patch.object(Evaluator, "_process_audio_files_with_verification")
    @patch.object(Evaluator, "_upload_session_json")
    @patch.object(Evaluator, "_cleanup")
    def test_close_calls_all_cleanup_methods_for_nmos(
        self,
        mock_cleanup: Mock,
        mock_upload_session: Mock,
        mock_process: Mock,
        mock_wait: Mock,
    ):
        # Given
        self.evaluator._initialized = True  # type: ignore
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore

        # When
        result = self.evaluator.close()

        # Then
        mock_wait.assert_called_once()
        mock_process.assert_called_once()
        mock_upload_session.assert_called_once()
        mock_cleanup.assert_called_once()
        self.assertEqual(result, {"status": "ok"})

    @patch.object(Evaluator, "_update_ranking_batch_size_before_upload")
    @patch.object(Evaluator, "_wait_for_uploads")
    @patch.object(Evaluator, "_process_audio_files_with_verification")
    @patch.object(Evaluator, "_upload_session_json")
    @patch.object(Evaluator, "_cleanup")
    def test_close_calls_update_batch_size_for_ranking(
        self,
        mock_cleanup: Mock,
        mock_upload_session: Mock,
        mock_process: Mock,
        mock_wait: Mock,
        mock_update_batch: Mock,
    ):
        # Given
        self.evaluator._initialized = True  # type: ignore
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore

        # When
        result = self.evaluator.close()

        # Then
        mock_update_batch.assert_called_once()
        mock_wait.assert_called_once()
        mock_process.assert_called_once()
        mock_upload_session.assert_called_once()
        mock_cleanup.assert_called_once()
        self.assertEqual(result, {"status": "ok"})

    def test_add_file_raises_error_when_not_initialized(self):
        """Test add_file raises error when evaluator is not initialized"""
        # Given
        self.evaluator._initialized = False  # type: ignore
        file = File(path=self.test_wav, model_tag="test_model")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_file(file)
        self.assertIn("add file once the evaluator is closed", str(context.exception))

    def test_add_file_raises_error_for_wrong_eval_type(self):
        """Test add_file raises error for non-single evaluation types"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.PREF  # type: ignore
        file = File(path=self.test_wav, model_tag="test_model")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_file(file)
        self.assertIn("single file evaluation types", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_file_processes_file_successfully(self, mock_upload: Mock):
        """Test add_file processes and uploads file successfully"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        file = File(path=self.test_wav, model_tag="test_model")

        # When
        self.evaluator.add_file(file)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)  # type: ignore
        mock_upload.assert_called_once()

    def test_add_files_raises_error_when_not_initialized(self):
        """Test add_files raises error when evaluator is not initialized"""
        # Given
        self.evaluator._initialized = False  # type: ignore
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_files(file0, file1)
        self.assertIn("Evaluator is not initialized", str(context.exception))

    def test_add_files_raises_error_for_wrong_eval_type(self):
        """Test add_files raises error for non-comparison evaluation types"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_files(file0, file1)
        self.assertIn("comparison evaluation types", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_files_processes_two_files_successfully(self, mock_upload: Mock):
        """Test add_files processes and uploads two files successfully"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.PREF  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.PREF]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When
        self.evaluator.add_files(file0, file1)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)  # type: ignore
        self.assertEqual(mock_upload.call_count, 2)

    def test_add_ranking_set_raises_error_when_not_initialized(self):
        """Test add_ranking_set raises error when evaluator is not initialized"""
        # Given
        self.evaluator._initialized = False  # type: ignore
        files = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("Evaluator is not initialized", str(context.exception))

    def test_add_ranking_set_raises_error_for_wrong_eval_type(self):
        """Test add_ranking_set raises error for non-RANKING evaluation types"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        files = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("ranking evaluation types", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_processes_files_successfully(self, mock_upload: Mock):
        """Test add_ranking_set processes and uploads ranking files successfully"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        files = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
        ]

        # When
        self.evaluator.add_ranking_set(files)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)  # type: ignore
        self.assertEqual(mock_upload.call_count, 2)

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_inconsistent_model_tag_order(
        self, mock_upload: Mock
    ):
        """Test add_ranking_set rejects files with inconsistent model_tag order across groups"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # First group: A, B
        files1 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
        ]
        self.evaluator.add_ranking_set(files1)

        # Second group: B, A (reversed order - should fail)
        files2 = [
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="A"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files2)
        self.assertIn("identical model_tag order", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_inconsistent_group_size(self, mock_upload: Mock):
        """Test add_ranking_set rejects groups with different number of files"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # First group: 2 files
        files1 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
        ]
        self.evaluator.add_ranking_set(files1)

        # Second group: 3 files (should fail)
        files2 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files2)
        self.assertIn("consistent group size", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_single_file(self, mock_upload: Mock):
        """Test add_ranking_set rejects a group with only one file"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Single file group (should fail)
        files = [File(path=self.test_wav, model_tag="A")]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("at least two files", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_reference_files(self, mock_upload: Mock):
        """Test add_ranking_set rejects files with is_ref=True"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Files with reference (should fail)
        files = [
            File(path=self.test_wav, model_tag="A", is_ref=True),
            File(path=self.test_wav, model_tag="B"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("cannot include reference files", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_maintains_order_across_multiple_groups(
        self, mock_upload: Mock
    ):
        """Test add_ranking_set maintains consistent order across multiple groups"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 3  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # First group: A, B, C
        files1 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
        ]
        self.evaluator.add_ranking_set(files1)

        # Second group: same order A, B, C (should pass)
        files2 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
        ]
        self.evaluator.add_ranking_set(files2)

        # Third group: same order A, B, C (should pass)
        files3 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
        ]
        self.evaluator.add_ranking_set(files3)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 3)  # type: ignore
        self.assertEqual(mock_upload.call_count, 9)  # 3 groups * 3 files each

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_duplicate_model_tags_exact(
        self, mock_upload: Mock
    ):
        """Test add_ranking_set rejects duplicate model_tags (exact match)"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Files with duplicate model_tag (should fail)
        files = [
            File(path=self.test_wav, model_tag="AWS"),
            File(path=self.test_wav, model_tag="AWS"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("unique model_tags within a group", str(context.exception))
        self.assertIn("Duplicate found: 'AWS'", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_duplicate_model_tags_case_insensitive(
        self, mock_upload: Mock
    ):
        """Test add_ranking_set rejects duplicate model_tags (case-insensitive)"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Files with duplicate model_tag in different case (should fail)
        files = [
            File(path=self.test_wav, model_tag="AWS"),
            File(path=self.test_wav, model_tag="aws"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("unique model_tags within a group", str(context.exception))
        self.assertIn("case-insensitive", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_rejects_duplicate_in_three_files(self, mock_upload: Mock):
        """Test add_ranking_set rejects duplicate model_tags in a group of three"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 3  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # First and last have duplicate tag (case-insensitive)
        files = [
            File(path=self.test_wav, model_tag="ModelA"),
            File(path=self.test_wav, model_tag="ModelB"),
            File(path=self.test_wav, model_tag="modela"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_ranking_set(files)
        self.assertIn("unique model_tags within a group", str(context.exception))

    def test_update_ranking_batch_size_raises_error_when_no_groups(self):
        """Test _update_ranking_batch_size_before_upload raises error when no groups"""
        # Given
        self.evaluator._ordered_file_groups = []  # type: ignore

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore
        self.assertIn("at least one group with files", str(context.exception))

    def test_update_ranking_batch_size_raises_error_when_group_too_small(self):
        """Test _update_ranking_batch_size_before_upload raises error when group has < 2 files"""
        # Given
        audio = Audio(
            path=self.test_wav,
            name="test.wav",
            remote_object_name="remote/test.wav",
            script=None,
            tags=[],
            model_tag="A",
            is_ref=False,
            group="group1",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        group = AudioGroup(group_id="group1", audios=[audio], created_at=datetime.now())
        self.evaluator._ordered_file_groups = [group]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore
        self.assertIn("at least two files per group", str(context.exception))

    def test_update_ranking_batch_size_updates_batch_size_successfully(self):
        """Test _update_ranking_batch_size_before_upload updates batch_size correctly"""
        # Given
        audios = [
            Audio(
                path=self.test_wav,
                name=f"test{i}.wav",
                remote_object_name=f"remote/test{i}.wav",
                script=None,
                tags=[],
                model_tag=chr(65 + i),  # A, B, C
                is_ref=False,
                group="group1",
                type=QuestionFileType.STIMULUS,
                order_in_group=i,
            )
            for i in range(3)
        ]
        group = AudioGroup(group_id="group1", audios=audios, created_at=datetime.now())
        self.evaluator._ordered_file_groups = [group]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        self.evaluator._evaluation_service = Mock()  # type: ignore
        self.evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        # When
        self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore

        # Then
        self.evaluator._evaluation_service.update_specific_fields.assert_called_once()  # type: ignore
        call_args = self.evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        payload = call_args[0][1]
        self.assertEqual(payload["batch_size"], 3)
        self.assertEqual(call_args.kwargs["timeout"], self.evaluator._eval_config.api_timeout)  # type: ignore
        self.assertEqual(
            call_args.kwargs["context"]["operation"],
            "ranking_batch_size_resolution",
        )
        self.assertEqual(self.evaluator._eval_config.eval_batch_size, 3)  # type: ignore

    @patch.object(Evaluator, "_upload_one_file")
    def test_resume_upload_ranking_persists_batch_size_before_first_upload(
        self, mock_upload: Mock
    ):
        """Regression: crash after first RANKING upload must not leave batch_size=2."""
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "ranking-resume.sqlite")
        evaluation_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        ranking_evaluation = EvaluationEntity(
            id=evaluation_id,
            title="ranking",
            internal_name=None,
            description=None,
            batch_size=2,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )
        eval_config = EvalConfig(
            type=EvalType.RANKING.value,
            resume_upload=True,
            upload_state_path=state_path,
            api_timeout=(8, 88),
        )
        with patch.object(Evaluator, "_set_evaluation", return_value=ranking_evaluation):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.RANKING],
            )
        evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        evaluator.add_ranking_set(
            [
                File(path=self.test_wav, model_tag="A"),
                File(path=self.test_wav, model_tag="B"),
                File(path=self.test_wav, model_tag="C"),
            ]
        )

        evaluator._evaluation_service.update_specific_fields.assert_called_once()  # type: ignore
        call_args = evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        self.assertEqual(call_args[0][0], evaluation_id)
        self.assertEqual(call_args[0][1]["batch_size"], 3)
        self.assertEqual(call_args.kwargs["timeout"], (8, 88))
        self.assertEqual(
            call_args.kwargs["context"]["operation"],
            "ranking_batch_size_resolution",
        )
        self.assertEqual(mock_upload.call_count, 3)
        contract = UploadLedger(state_path).get_evaluation_contract(evaluation_id)
        self.assertIsNotNone(contract)
        self.assertEqual(contract["eval_batch_size"], 3)  # type: ignore[index]
        self.assertEqual(evaluator._eval_config.eval_batch_size, 3)  # type: ignore

    @patch.object(Evaluator, "_upload_one_file")
    def test_update_specific_fields_receives_correct_batch_size_from_add_ranking_set(
        self, mock_upload: Mock
    ):
        """Test that batch_size in update_specific_fields matches the number of files added via add_ranking_set"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Add 4 files in the ranking set
        files = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
            File(path=self.test_wav, model_tag="D"),
        ]
        self.evaluator.add_ranking_set(files)

        # Mock the evaluation service for update_specific_fields
        self.evaluator._evaluation_service = Mock()  # type: ignore
        self.evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        # When
        self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore

        # Then
        self.evaluator._evaluation_service.update_specific_fields.assert_called_once()  # type: ignore
        call_args = self.evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        payload = call_args[0][1]

        # Verify batch_size matches the number of files added
        self.assertEqual(
            payload["batch_size"],
            4,
            "batch_size should match the number of files in add_ranking_set",
        )
        self.assertEqual(len(self.evaluator._ordered_file_groups[0].audios), 4)  # type: ignore
        self.assertEqual(self.evaluator._eval_config.eval_batch_size, 4)  # type: ignore

    @patch.object(Evaluator, "_upload_one_file")
    def test_update_specific_fields_batch_size_matches_first_group_size(
        self, mock_upload: Mock
    ):
        """Test that batch_size is determined by the first group's file count"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Add first group with 5 files
        files1 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
            File(path=self.test_wav, model_tag="D"),
            File(path=self.test_wav, model_tag="E"),
        ]
        self.evaluator.add_ranking_set(files1)

        # Add second group with same files
        files2 = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
            File(path=self.test_wav, model_tag="D"),
            File(path=self.test_wav, model_tag="E"),
        ]
        self.evaluator.add_ranking_set(files2)

        # Mock the evaluation service
        self.evaluator._evaluation_service = Mock()  # type: ignore
        self.evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        # When
        self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore

        # Then
        self.evaluator._evaluation_service.update_specific_fields.assert_called_once()  # type: ignore
        call_args = self.evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        payload = call_args[0][1]

        # Verify batch_size is 5 (from first group)
        self.assertEqual(
            payload["batch_size"], 5, "batch_size should be 5 from the first group"
        )
        self.assertEqual(len(self.evaluator._ordered_file_groups), 2)  # type: ignore
        self.assertEqual(len(self.evaluator._ordered_file_groups[0].audios), 5)  # type: ignore
        self.assertEqual(len(self.evaluator._ordered_file_groups[1].audios), 5)  # type: ignore

    @patch.object(Evaluator, "_upload_one_file")
    def test_update_specific_fields_payload_structure_for_ranking(
        self, mock_upload: Mock
    ):
        """Test that update_specific_fields receives correct payload structure for RANKING"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore

        # Add 3 files
        files = [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag="C"),
        ]
        self.evaluator.add_ranking_set(files)

        # Mock the evaluation service
        self.evaluator._evaluation_service = Mock()  # type: ignore
        self.evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        # When
        self.evaluator._update_ranking_batch_size_before_upload()  # type: ignore

        # Then
        call_args = self.evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        eval_id = call_args[0][0]
        payload = call_args[0][1]

        # Verify all required fields in payload
        self.assertEqual(eval_id, "test_id")
        self.assertEqual(payload["id"], "test_id")
        self.assertEqual(payload["batch_size"], 3)
        self.assertEqual(payload["evaluation_type"], "SPEECH_RANKING")
        self.assertEqual(payload["build_process"], "FILE_UPLOAD")
        self.assertIn("language", payload)
        self.assertIn("meta_data", payload)
        self.assertEqual(payload["meta_data"], {})

    def test_verify_files_in_batches_with_custom_batch_size(self):
        """Test _verify_files_in_batches respects custom verify_batch_size from config."""
        # Given
        custom_batch_size = 100
        eval_config = EvalConfig(
            type=EvalType.NMOS.value, verify_batch_size=custom_batch_size
        )

        with patch.object(
            Evaluator, "_set_evaluation", return_value=self.mock_evaluation
        ):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.NMOS],
            )

        total_files = 350  # Should create 4 batches: 100 + 100 + 100 + 50
        audios = [self._create_test_audio(i) for i in range(total_files)]
        mock_service = Mock()

        def mock_verify_files(eval_id: str, batch: List[Audio], *args, **kwargs) -> VerifyFilesResponse:
            return self._create_mock_verify_response(batch)

        mock_service.verify_files.side_effect = mock_verify_files
        evaluator._evaluation_service = mock_service  # type: ignore

        # When
        result = evaluator._verify_files_in_batches("eval_id", audios)  # type: ignore

        # Then
        self.assertEqual(mock_service.verify_files.call_count, 4)  # 4 batches

        # Verify batch sizes
        calls = mock_service.verify_files.call_args_list
        self.assertEqual(len(calls[0][0][1]), 100)  # First batch
        self.assertEqual(len(calls[1][0][1]), 100)  # Second batch
        self.assertEqual(len(calls[2][0][1]), 100)  # Third batch
        self.assertEqual(len(calls[3][0][1]), 50)  # Fourth batch

        # Verify aggregated results
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, total_files)

    def test_eval_config_verify_batch_size_default(self):
        """Test EvalConfig uses default verify_batch_size when not specified."""
        # Given/When
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        # Then
        self.assertEqual(eval_config.verify_batch_size, EvalConfigDefault.VERIFY_BATCH_SIZE)
        self.assertEqual(eval_config.verify_batch_size, 100)

    def test_eval_config_verify_batch_size_custom(self):
        """Test EvalConfig accepts custom verify_batch_size."""
        # Given/When
        eval_config = EvalConfig(type=EvalType.NMOS.value, verify_batch_size=200)

        # Then
        self.assertEqual(eval_config.verify_batch_size, 200)

    def test_eval_config_verify_batch_size_validation_too_low(self):
        """Test EvalConfig rejects verify_batch_size < 1."""
        # When/Then - 0 raises FailedCheckException from glog
        with self.assertRaises(FailedCheckException):
            EvalConfig(type=EvalType.NMOS.value, verify_batch_size=0)

    def test_eval_config_verify_batch_size_validation_too_high(self):
        """Test EvalConfig rejects verify_batch_size > 1000."""
        # When/Then
        with self.assertRaises(ValueError) as context:
            EvalConfig(type=EvalType.NMOS.value, verify_batch_size=1001)
        self.assertIn("verify_batch_size", str(context.exception).lower())

    def test_verify_batch_size_boundary_values(self):
        """Test verify_batch_size accepts boundary values (1 and 1000)."""
        # Given/When/Then - minimum value
        eval_config_min = EvalConfig(type=EvalType.NMOS.value, verify_batch_size=1)
        self.assertEqual(eval_config_min.verify_batch_size, 1)

        # Given/When/Then - maximum value
        eval_config_max = EvalConfig(type=EvalType.NMOS.value, verify_batch_size=1000)
        self.assertEqual(eval_config_max.verify_batch_size, 1000)

    def test_eval_config_timeout_defaults(self):
        """Test EvalConfig exposes client-local timeout defaults."""
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        self.assertEqual(eval_config.api_timeout, (5, 30))
        self.assertEqual(eval_config.verify_timeout, (5, 120))
        self.assertEqual(eval_config.upload_timeout, (10, 300))

    def test_eval_config_timeout_custom_and_validation(self):
        """Test EvalConfig accepts custom timeout tuples and rejects invalid values."""
        eval_config = EvalConfig(
            type=EvalType.NMOS.value,
            api_timeout=(1, 2),
            verify_timeout=(3, 4),
            upload_timeout=(5, 6),
        )

        self.assertEqual(eval_config.api_timeout, (1, 2))
        self.assertEqual(eval_config.verify_timeout, (3, 4))
        self.assertEqual(eval_config.upload_timeout, (5, 6))

        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, verify_timeout=(0, 10))
        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, upload_timeout=(10, 1))
        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, api_timeout=(True, 30))
        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, api_timeout=(float("nan"), 30))
        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, api_timeout=(5, float("inf")))

    def test_eval_config_timeouts_are_client_local_not_serialized(self):
        """Timeout config should not leak into session JSON / backend DTOs."""
        eval_config = EvalConfig(
            type=EvalType.NMOS.value,
            api_timeout=(1, 2),
            verify_timeout=(3, 4),
            upload_timeout=(5, 6),
        )

        self.assertNotIn("api_timeout", eval_config.to_dict())
        self.assertNotIn("verify_timeout", eval_config.to_dict())
        self.assertNotIn("upload_timeout", eval_config.to_dict())
        self.assertNotIn("api_timeout", eval_config.to_create_request_dto())
        self.assertNotIn("verify_timeout", eval_config.to_create_request_dto())
        self.assertNotIn("upload_timeout", eval_config.to_create_request_dto())

    def test_eval_config_upload_ledger_defaults_are_opt_in(self):
        """Ledger/resume config defaults off and does not require a state path."""
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        self.assertFalse(eval_config.resume_upload)
        self.assertIsNone(eval_config.upload_state_path)
        self.assertEqual(
            eval_config.resolve_upload_state_path(),
            os.path.join(os.getcwd(), ".podonos_upload_state.sqlite"),
        )

    def test_eval_config_upload_ledger_custom_values_and_validation(self):
        """Ledger/resume config accepts explicit opt-in values and validates types."""
        eval_config = EvalConfig(
            type=EvalType.NMOS.value,
            resume_upload=True,
            upload_state_path="/tmp/podonos-state.sqlite",
        )

        self.assertTrue(eval_config.resume_upload)
        self.assertEqual(eval_config.upload_state_path, "/tmp/podonos-state.sqlite")
        self.assertEqual(
            eval_config.resolve_upload_state_path(), "/tmp/podonos-state.sqlite"
        )

        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, resume_upload="yes")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            EvalConfig(type=EvalType.NMOS.value, upload_state_path="")

    def test_eval_config_upload_ledger_is_client_local_not_serialized(self):
        """Ledger path and resume flag should not leak into backend DTOs/session JSON."""
        eval_config = EvalConfig(
            type=EvalType.NMOS.value,
            resume_upload=True,
            upload_state_path="/tmp/podonos-state.sqlite",
        )

        for key in ("resume_upload", "upload_state_path"):
            self.assertNotIn(key, eval_config.to_dict())
            self.assertNotIn(key, eval_config.to_create_request_dto())
            self.assertNotIn(key, eval_config.to_create_from_template_request_dto())


    # ----------------------------
    # script_tags RANKING-only enforcement tests
    # ----------------------------
    @patch.object(Evaluator, "_upload_one_file")
    def test_add_file_rejects_non_empty_script_tags(self, mock_upload: Mock):
        """Test add_file raises ValueError when file has non-empty script_tags"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        file = File(path=self.test_wav, model_tag="test_model", script_tags=["address"])

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_file(file)
        self.assertIn("script_tags is only supported for RANKING", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_file_allows_empty_script_tags(self, mock_upload: Mock):
        """Test add_file succeeds when file has empty script_tags (regression guard)"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.NMOS  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        file = File(path=self.test_wav, model_tag="test_model", script_tags=[])

        # When
        self.evaluator.add_file(file)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)  # type: ignore
        mock_upload.assert_called_once()

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_files_rejects_non_empty_script_tags(self, mock_upload: Mock):
        """Test add_files raises ValueError when any file has non-empty script_tags"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.PREF  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.PREF]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        file0 = File(path=self.test_wav, model_tag="model1", script_tags=["address"])
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator.add_files(file0, file1)
        self.assertIn("script_tags is only supported for RANKING", str(context.exception))

    @patch.object(Evaluator, "_upload_one_file")
    def test_add_ranking_set_allows_script_tags(self, mock_upload: Mock):
        """Test add_ranking_set succeeds with script_tags"""
        # Given
        self.evaluator._eval_config._eval_type = EvalType.RANKING  # type: ignore
        self.evaluator._eval_config._eval_batch_size = 2  # type: ignore
        self.evaluator._supported_eval_types = [EvalType.RANKING]  # type: ignore
        self.evaluator._evaluation = self.mock_evaluation  # type: ignore
        files = [
            File(path=self.test_wav, model_tag="A", script_tags=["address"]),
            File(path=self.test_wav, model_tag="B", script_tags=["address"]),
        ]

        # When
        self.evaluator.add_ranking_set(files)

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)  # type: ignore
        self.assertEqual(mock_upload.call_count, 2)


class TestEvaluatorRankingRef(unittest.TestCase):
    """RANKING_REF resume and call-ordering."""

    def setUp(self):
        self.test_wav = TESTDATA_SPEECH_TWO_CH1_WAV
        self.api_client = Mock(spec=APIClient)
        self.state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)

    def _evaluator(self, evaluation_id: str, state_path: str, eval_type: EvalType):
        current_time = datetime.now(timezone.utc)
        evaluation = EvaluationEntity(
            id=evaluation_id,
            title="ranking ref",
            internal_name=None,
            description=None,
            batch_size=2,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )
        eval_config = EvalConfig(
            type=eval_type.value,
            resume_upload=True,
            upload_state_path=state_path,
        )
        with patch.object(Evaluator, "_set_evaluation", return_value=evaluation):
            return Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[eval_type],
            )

    def _ranking_ref_group(self, ref_tag: str = "reference"):
        return [
            File(path=self.test_wav, model_tag="A"),
            File(path=self.test_wav, model_tag="B"),
            File(path=self.test_wav, model_tag=ref_tag, is_ref=True),
        ]

    @patch.object(Evaluator, "_upload_one_file")
    def test_resume_upload_round_trips_a_reference_bearing_group(
        self, mock_upload: Mock
    ):
        """The ledger contract must record the reference-inclusive batch_size."""
        state_path = os.path.join(self.state_dir.name, "ranking-ref-resume.sqlite")
        evaluation_id = str(uuid4())
        evaluator = self._evaluator(evaluation_id, state_path, EvalType.RANKING_REF)
        evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        evaluator.add_ranking_set(self._ranking_ref_group())

        call_args = evaluator._evaluation_service.update_specific_fields.call_args  # type: ignore
        self.assertEqual(call_args[0][1]["batch_size"], 3)
        self.assertEqual(call_args[0][1]["evaluation_type"], "SPEECH_RANKING_REF")
        self.assertEqual(mock_upload.call_count, 3)

        contract = UploadLedger(state_path).get_evaluation_contract(evaluation_id)
        self.assertIsNotNone(contract)
        self.assertEqual(contract["eval_type"], EvalType.RANKING_REF.value)  # type: ignore[index]
        self.assertEqual(contract["eval_batch_size"], 3)  # type: ignore[index]

    @patch.object(Evaluator, "_upload_one_file")
    def test_batch_size_resolution_is_logged_on_the_success_path(
        self, _mock_upload: Mock
    ):
        """The only SDK-side trace of a contract that is otherwise silent when wrong."""
        state_path = os.path.join(self.state_dir.name, "ranking-ref-log.sqlite")
        evaluator = self._evaluator(str(uuid4()), state_path, EvalType.RANKING_REF)
        evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        with self.assertLogs(level="INFO") as captured:
            evaluator.add_ranking_set(self._ranking_ref_group())

        self.assertTrue(
            any(
                "Ranking batch_size resolved: type=SPEECH_RANKING_REF batch_size=3"
                in line
                for line in captured.output
            ),
            captured.output,
        )

    @patch.object(Evaluator, "_upload_one_file")
    def test_batch_size_patch_precedes_file_metadata_registration(
        self, _mock_upload: Mock
    ):
        """The PATCH reaches the backend's delete-all-files path.

        It is only harmless because it is sent before any file metadata exists.
        If close() ever registers metadata first, the backend wipes the files.
        """
        state_path = os.path.join(self.state_dir.name, "ranking-ref-order.sqlite")
        evaluator = self._evaluator(str(uuid4()), state_path, EvalType.RANKING_REF)

        service = Mock()
        service.process_files.return_value.processing_count = 6
        evaluator._evaluation_service = service  # type: ignore

        manager = Mock()
        manager.attach_mock(service.update_specific_fields, "patch_fields")

        with patch.object(
            Evaluator, "_register_metadata_for_audios"
        ) as mock_register, patch.object(
            Evaluator, "_wait_for_uploads"
        ), patch.object(
            Evaluator, "_verify_files_in_batches"
        ), patch.object(
            Evaluator, "_upload_session_json"
        ), patch.object(
            Evaluator, "_cleanup"
        ):
            manager.attach_mock(mock_register, "register")
            evaluator.add_ranking_set(self._ranking_ref_group())
            evaluator.add_ranking_set(self._ranking_ref_group())
            evaluator.close()

        names = [name for name, _args, _kwargs in manager.mock_calls]
        self.assertIn("patch_fields", names)
        self.assertIn("register", names)
        self.assertLess(names.index("patch_fields"), names.index("register"))


if __name__ == "__main__":
    unittest.main()
