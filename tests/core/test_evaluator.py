import os
import unittest
from datetime import datetime, timezone
from typing import List
from unittest.mock import Mock, patch

from glog import FailedCheckException

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import Audio, AudioGroup, File
from podonos.entity.evaluation import EvaluationEntity
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
        with patch.object(Evaluator, "_set_evaluation", return_value=self.mock_evaluation):
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
        with patch.object(Evaluator, "_set_evaluation", return_value=self.mock_evaluation):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.NMOS],
            )

        # Then
        self.assertEqual(evaluator._eval_config, eval_config)  # type: ignore
        self.assertTrue(evaluator._initialized)  # type: ignore
        self.assertEqual(evaluator._ordered_file_groups, [])  # type: ignore

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
        self.api_client.post.return_value = Mock(status_code=200, json=lambda: mock_response)

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
        self.api_client.post.return_value = Mock(status_code=200, json=lambda: mock_response)
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

    def test_should_cleanup_successfully(self):
        # Given
        self.evaluator._initialized = True  # type: ignore
        self.evaluator._ordered_file_groups = [AudioGroup(group_id="group1", audios=[], created_at=datetime.now())]  # type: ignore

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
        group = AudioGroup(group_id="test_group", audios=[audio], created_at=datetime.now())
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
            self.evaluator._validate_initialization(self.api_client, None, [EvalType.NMOS])  # type: ignore

    def test_validate_initialization_with_unsupported_eval_type(self):
        """Test _validate_initialization raises error for unsupported eval type"""
        # Given
        eval_config = EvalConfig(type=EvalType.PREF.value)

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_initialization(self.api_client, eval_config, [EvalType.NMOS])  # type: ignore
        self.assertIn("Not supported evaluation type", str(context.exception))

    def test_initialize_attributes_sets_all_attributes(self):
        """Test _initialize_attributes properly sets all class attributes"""
        # Given
        eval_config = EvalConfig(type=EvalType.NMOS.value)
        evaluator = object.__new__(Evaluator)  # Create uninitialized instance

        # When
        with patch.object(Evaluator, "_set_evaluation", return_value=self.mock_evaluation):
            evaluator._initialize_attributes(self.api_client, eval_config, [EvalType.NMOS])  # type: ignore

        # Then
        self.assertEqual(evaluator._api_client, self.api_client)  # type: ignore
        self.assertEqual(evaluator._eval_config, eval_config)  # type: ignore
        self.assertIsNotNone(evaluator._evaluation_service)  # type: ignore
        self.assertIsNotNone(evaluator._file_transformer)  # type: ignore
        self.assertIsNotNone(evaluator._file_validator)  # type: ignore
        self.assertEqual(evaluator._supported_eval_types, [EvalType.NMOS])  # type: ignore
        self.assertEqual(evaluator._ordered_file_groups, [])  # type: ignore
        self.assertIsNone(evaluator._upload_manager)  # type: ignore

    @patch("podonos.core.evaluator.UploadManager")
    def test_upload_one_file_initializes_upload_manager_lazily(self, mock_upload_manager: Mock):
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
        mock_upload_manager.add_file_to_queue.assert_called_once_with("eval_id", test_audio)

    def test_process_audio_files_with_verification_batches_correctly(self):
        # Given
        groups: List[AudioGroup] = []
        for i in range(600):
            group_id = f"group{i}"
            audio = Audio(
                path=self.test_wav,
                name=f"test{i}.wav",
                remote_object_name=f"remote/test{i}.wav",
                script=None,
                tags=[],
                model_tag="test_model",
                is_ref=False,
                group=group_id,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)
            group = AudioGroup(group_id=group_id, audios=[audio], created_at=datetime.now())
            groups.append(group)

        self.evaluator._ordered_file_groups = groups  # type: ignore
        mock_service = Mock()
        mock_service.verify_files.return_value = Mock(all_verified=True, verified_count=600)
        mock_service.process_files.return_value = Mock(processing_count=600)
        self.evaluator._evaluation_service = mock_service  # type: ignore
        self.evaluator._upload_manager = None  # type: ignore

        # When
        self.evaluator._process_audio_files_with_verification()  # type: ignore

        # Then
        self.assertEqual(mock_service.create_evaluation_files.call_count, 2)

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


if __name__ == "__main__":
    unittest.main()
