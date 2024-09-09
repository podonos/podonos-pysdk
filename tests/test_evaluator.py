import os
import unittest
import requests

from datetime import datetime
from typing import Optional
from unittest.mock import Mock, patch, MagicMock

from podonos.common.enum import QuestionFileType
from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from tests.test_audio import TESTDATA_SPEECH_CH1_MP3


class MockEvaluator(Evaluator):
    def __init__(self, api_client=Mock(spec=APIClient), eval_config: Optional[EvalConfig] = None):
        super().__init__(api_client, eval_config)

    def add_file(self, file: File) -> None:
        pass

    def add_files(self, target: File, ref: File) -> None:
        pass

    def _create_evaluation(self) -> Evaluation:
        evaluation_config = {
            "id": "mock_id",
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-05-21T06:18:09.659270Z",
            "updated_time": "2024-05-22T06:18:09.659270Z",
        }
        evaluation = Evaluation.from_dict(evaluation_config)
        return evaluation


class TestEvaluator(unittest.TestCase):

    def setUp(self):
        self.eval_config = EvalConfig(type="NMOS")
        self.evaluator = MockEvaluator(eval_config=self.eval_config)

    def test_get_eval_config_success(self):
        eval_config = EvalConfig(type="NMOS")
        evaluator = MockEvaluator(eval_config=eval_config)

        result = evaluator._get_eval_config()
        self.assertEqual(result, eval_config)

    def test_get_eval_config_not_initialized(self):
        evaluator = MockEvaluator(eval_config=None)

        with self.assertRaises(ValueError) as context:
            evaluator._get_eval_config()

        self.assertEqual(str(context.exception), "Evaluator is not initialized")

    def test_create_evaluation_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None  # No exception
        mock_response.json.return_value = {
            "id": "123",
            "title": "title",
            "internal_name": None,
            "description": None,
            "status": "DRAFT",
            "created_time": datetime.now().isoformat(),
            "updated_time": datetime.now().isoformat(),
        }

        eval_config = EvalConfig("NMOS")
        evaluator = MockEvaluator(api_client=MagicMock(), eval_config=eval_config)
        evaluator._api_client.post.return_value = mock_response  # type: ignore

        evaluation = evaluator._create_evaluation()

        self.assertEqual(evaluation.id, "mock_id")

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_set_audio(self, mock_access, mock_isfile):
        audio_file = File(path=TESTDATA_SPEECH_CH1_MP3, model_tag="model1", tags=["tag1", "tag2"], script="Hello World")
        group = "group1"
        type = QuestionFileType.STIMULUS
        order_in_group = 0
        audio = self.evaluator._set_audio(audio_file, group, type, order_in_group)
        posix_style_path = TESTDATA_SPEECH_CH1_MP3.replace("\\", "/")

        self.assertEqual(audio.path, audio_file.path)
        self.assertEqual(audio.name, posix_style_path)
        self.assertEqual(audio.model_tag, audio_file.model_tag)
        self.assertEqual(audio.tags, audio_file.tags)
        self.assertEqual(audio.script, audio_file.script)
        self.assertEqual(audio.group, group)
        self.assertEqual(audio.type, type)
        self.assertEqual(audio.order_in_group, order_in_group)

    @patch("os.path.isfile")
    @patch("os.access")
    def test_validate_path_success(self, mock_access, mock_isfile):
        mock_isfile.return_value = True
        mock_access.return_value = True

        evaluator = MockEvaluator(eval_config=EvalConfig(type="NMOS"))

        valid_path = "/valid/path/to/file.txt"
        result = evaluator._validate_path(valid_path)
        self.assertEqual(result, valid_path)

        mock_isfile.assert_called_once_with(valid_path)
        mock_access.assert_called_once_with(valid_path, os.R_OK)

    @patch("os.path.isfile")
    @patch("os.access")
    def test_validate_path_file_not_exist(self, mock_access, mock_isfile):
        mock_isfile.return_value = False
        evaluator = MockEvaluator(api_client=MagicMock(), eval_config=EvalConfig(type="NMOS"))

        invalid_path = "/invalid/path/to/file.txt"
        with self.assertRaises(FileNotFoundError) as context:
            evaluator._validate_path(invalid_path)

        self.assertIn("doesn't exist", str(context.exception))

        mock_isfile.assert_called_once_with(invalid_path)
        mock_access.assert_not_called()

    @patch("os.path.isfile")
    @patch("os.access")
    def test_validate_path_not_readable(self, mock_access, mock_isfile):
        mock_isfile.return_value = True
        mock_access.return_value = False

        evaluator = MockEvaluator(eval_config=EvalConfig(type="NMOS"))

        unreadable_path = "/unreadable/path/to/file.txt"
        with self.assertRaises(FileNotFoundError) as context:
            evaluator._validate_path(unreadable_path)

        self.assertIn("isn't readable", str(context.exception))

        mock_isfile.assert_called_once_with(unreadable_path)
        mock_access.assert_called_once_with(unreadable_path, os.R_OK)

    def test_paths(self):
        test_cases = [
            # Test case: paths with backslashes
            {
                "original_path": r"C:\Users\Example\Documents\file.txt",
                "remote_object_path": r"C:\Files\Other\file.txt",
                "expected_original_path": "C:/Users/Example/Documents/file.txt",
                "expected_remote_object_path": "C:/Files/Other/file.txt",
            },
            # Test case: paths with forward slashes
            {
                "original_path": "C:/Users/Example/Documents/file.txt",
                "remote_object_path": "C:/Files/Other/file.txt",
                "expected_original_path": "C:/Users/Example/Documents/file.txt",
                "expected_remote_object_path": "C:/Files/Other/file.txt",
            },
            # Test case: paths with mixed slashes
            {
                "original_path": r"C:\Users/Example\Documents/file.txt",
                "remote_object_path": r"C:/Files\Other\file.txt",
                "expected_original_path": "C:/Users/Example/Documents/file.txt",
                "expected_remote_object_path": "C:/Files/Other/file.txt",
            },
        ]

        for case in test_cases:
            posix_original_path, posix_remote_object_path = self.evaluator._process_original_path_and_remote_object_path_into_posix_style(
                case["original_path"], case["remote_object_path"]
            )

            self.assertEqual(posix_original_path, case["expected_original_path"])
            self.assertEqual(posix_remote_object_path, case["expected_remote_object_path"])


if __name__ == "__main__":
    unittest.main()
