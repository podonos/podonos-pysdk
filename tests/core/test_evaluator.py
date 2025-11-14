import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from podonos.common.enum import QuestionFileType, EvalType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import Audio, AudioGroup
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
            self.evaluator = Evaluator(api_client=self.api_client, eval_config=self.eval_config, supported_eval_types=[EvalType.NMOS])

        self.test_wav = TESTDATA_SPEECH_TWO_CH1_WAV

    def test_should_initialize_evaluator_successfully(self):
        # Given
        eval_config = EvalConfig(type=EvalType.NMOS.value)

        # When
        with patch.object(Evaluator, "_set_evaluation", return_value=self.mock_evaluation):
            evaluator = Evaluator(api_client=self.api_client, eval_config=eval_config, supported_eval_types=[EvalType.NMOS])

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
        self.assertIn("The 'add_file' is only supported for single file evaluation types:", str(context.exception))

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
            self.evaluator._evaluation.id, self.evaluator._eval_config, self.evaluator._ordered_file_groups  # type: ignore
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
        self.evaluator._upload_manager.get_upload_time.return_value = (upload_start, upload_finish)  # type: ignore

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


if __name__ == "__main__":
    unittest.main()
