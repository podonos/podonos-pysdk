import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from podonos.common.enum import QuestionFileType, EvalType
from podonos.core.api import APIClient
from podonos.core.audio import Audio, AudioGroup
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from tests.core.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV


class TestEvaluator(unittest.TestCase):
    def setUp(self):
        # Mock API client
        self.api_client = Mock(spec=APIClient)

        # Create mock evaluation
        current_time = datetime.now(timezone.utc)
        self.mock_evaluation = Evaluation(
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
        self.assertEqual(evaluator._eval_config, eval_config)
        self.assertTrue(evaluator._initialized)
        self.assertEqual(evaluator._ordered_file_groups, [])

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
        evaluation = self.evaluator._set_evaluation(self.eval_config)

        # Then
        self.assertIsInstance(evaluation, Evaluation)
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
        self.eval_config._eval_template_id = "test_template_id"

        # When
        evaluation = self.evaluator._set_evaluation(self.eval_config)

        # Then
        self.assertIsInstance(evaluation, Evaluation)
        self.assertEqual(evaluation.id, "test_id")
        self.assertEqual(evaluation.status, "DRAFT")

    def test_should_create_audio_successfully(self):
        # Given
        file = File(path=self.test_wav, model_tag="test_model", tags=["test"], script="test script")
        group = "test_group"
        type = QuestionFileType.STIMULUS
        order = 0

        # When
        audio = self.evaluator._create_audio(file, group, type, order)

        # Then
        self.assertEqual(audio.path, file.path)
        self.assertEqual(audio.model_tag, file.model_tag)
        self.assertEqual(audio.tags, file.tags)
        self.assertEqual(audio.script, file.script)
        self.assertEqual(audio.group, group)
        self.assertEqual(audio.type, type)
        self.assertEqual(audio.order_in_group, order)

    def test_should_add_audio_group_successfully(self):
        # Given
        group_id = "test_group"
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote/test.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        self.evaluator._add_audio_group(group_id, [audio])

        # Then
        self.assertEqual(len(self.evaluator._ordered_file_groups), 1)
        self.assertEqual(self.evaluator._ordered_file_groups[0].group_id, group_id)
        self.assertEqual(len(self.evaluator._ordered_file_groups[0].audios), 1)
        self.assertEqual(self.evaluator._ordered_file_groups[0].audios[0], audio)

    def test_should_validate_eval_type_successfully(self):
        # Test single file evaluation types
        assert self.evaluator._eval_config is not None
        self.evaluator._eval_config._eval_type = EvalType.NMOS
        self.evaluator._validate_eval_type("add_file")  # Should not raise

        # Test comparison evaluation types
        self.evaluator._eval_config._eval_type = EvalType.CMOS
        self.evaluator._validate_eval_type("add_files")  # Should not raise

    def test_should_validate_eval_type_raise_error(self):
        # Given
        self.evaluator._eval_config._eval_type = EvalType.CMOS

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_eval_type("add_file")
        self.assertIn("The 'add_file' is only supported for single file evaluation types:", str(context.exception))

    def test_should_validate_files_input_successfully(self):
        # Given
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2")
        self.evaluator._eval_config._eval_type = EvalType.PREF

        # When/Then
        self.evaluator._validate_files_input(file0, file1)  # Should not raise

    def test_should_validate_files_input_raise_error(self):
        # Given
        self.evaluator._eval_config._eval_type = EvalType.CMOS
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_files_input(file0, file1)
        self.assertEqual("One file must be reference, one must be stimulus", str(context.exception))

    def test_should_cleanup_successfully(self):
        # Given
        self.evaluator._initialized = True
        self.evaluator._ordered_file_groups = [AudioGroup(group_id="group1", audios=[], created_at=datetime.now())]

        # When
        self.evaluator._cleanup()

        # Then
        self.assertFalse(self.evaluator._initialized)
        self.assertEqual(self.evaluator._ordered_file_groups, [])

    @patch("podonos.service.evaluation_service.EvaluationService.upload_session_json")
    def test_should_upload_session_json_successfully(self, mock_upload):
        # Given
        self.evaluator._evaluation = Mock(id="test_eval_id")
        self.evaluator._evaluation_service = Mock()

        # When
        self.evaluator._upload_session_json()

        # Then
        self.evaluator._evaluation_service.upload_session_json.assert_called_once_with(
            self.evaluator._evaluation.id, self.evaluator._eval_config, self.evaluator._ordered_file_groups
        )

    def test_should_update_audio_upload_times(self):
        # Given
        audio = Mock(remote_object_name="test.wav")
        upload_start = {"test.wav": "2024-01-01T00:00:00Z"}
        upload_finish = {"test.wav": "2024-01-01T00:01:00Z"}

        # When
        self.evaluator._update_audio_upload_times(audio, upload_start, upload_finish)

        # Then
        audio.set_upload_at.assert_called_once_with(upload_start["test.wav"], upload_finish["test.wav"])

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
        self.evaluator._ordered_file_groups = [group]
        self.evaluator._upload_manager = Mock()
        upload_start = {"remote/test.wav": "2024-01-01T00:00:00Z"}
        upload_finish = {"remote/test.wav": "2024-01-01T00:01:00Z"}
        self.evaluator._upload_manager.get_upload_time.return_value = (upload_start, upload_finish)

        # When
        self.evaluator._process_upload_times()

        # Then
        self.assertEqual(audio._upload_start_at, upload_start["remote/test.wav"])
        self.assertEqual(audio._upload_finish_at, upload_finish["remote/test.wav"])

    def test_should_validate_close(self):
        # Given
        self.evaluator._initialized = True
        self.evaluator._upload_manager = Mock()

        # When/Then
        self.evaluator._validate_close()  # Should not raise

    def test_should_validate_close_raise_error(self):
        # Given
        self.evaluator._initialized = False

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.evaluator._validate_close()
        self.assertEqual(str(context.exception), "No evaluation session is open.")

    def test_should_create_reference_stimulus_pair(self):
        # Given
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2")
        group_id = "test_group"

        # When
        audio_pair = self.evaluator._create_reference_stimulus_pair(file0, file1, group_id)

        # Then
        self.assertEqual(len(audio_pair), 2)
        self.assertEqual(audio_pair[0].type, QuestionFileType.REF)
        self.assertEqual(audio_pair[1].type, QuestionFileType.STIMULUS)

    def test_should_create_stimulus_pair(self):
        # Given
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")
        group_id = "test_group"

        # When
        audio_pair = self.evaluator._create_stimulus_pair(file0, file1, group_id)

        # Then
        self.assertEqual(len(audio_pair), 2)
        self.assertEqual(audio_pair[0].type, QuestionFileType.STIMULUS)
        self.assertEqual(audio_pair[1].type, QuestionFileType.STIMULUS)

    def test_should_create_audio_pair(self):
        # Given
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")
        group_id = "test_group"

        # Test for PREF type
        assert self.evaluator._eval_config is not None
        self.evaluator._eval_config._eval_type = EvalType.PREF
        audio_pair = self.evaluator._create_audio_pair(file0, file1, group_id)
        self.assertEqual(len(audio_pair), 2)
        self.assertTrue(all(a.type == QuestionFileType.STIMULUS for a in audio_pair))

        # Test for CMOS type with reference
        self.evaluator._eval_config._eval_type = EvalType.CMOS
        file0._is_ref = True
        audio_pair = self.evaluator._create_audio_pair(file0, file1, group_id)
        self.assertEqual(len(audio_pair), 2)
        self.assertEqual(audio_pair[0].type, QuestionFileType.REF)
        self.assertEqual(audio_pair[1].type, QuestionFileType.STIMULUS)

    def test_should_needs_reference_file(self):
        # Test CMOS type (needs reference)
        assert self.evaluator._eval_config is not None
        self.evaluator._eval_config._eval_type = EvalType.CMOS
        self.assertTrue(self.evaluator._needs_reference_file())

        # Test PREF type (doesn't need reference)
        self.evaluator._eval_config._eval_type = EvalType.PREF
        self.assertFalse(self.evaluator._needs_reference_file())


if __name__ == "__main__":
    unittest.main()
