import unittest
from unittest.mock import Mock
from datetime import datetime, timezone

from podonos.service.evaluation_service import EvaluationService
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.common.enum import EvalType, Language, QuestionFileType
from podonos.common.exception import HTTPError
from podonos.core.audio import Audio
from tests.core.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV


class TestEvaluationService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = EvaluationService(self.mock_api_client)
        self.sample_eval_config = EvalConfig(
            name="test_eval", type=EvalType.NMOS.value, lan=Language.ENGLISH_AMERICAN.value, granularity=0.5, num_eval=10
        )
        self.test_audio = Audio(
            path=TESTDATA_SPEECH_TWO_CH1_WAV,
            name="speech_two_ch1.wav",
            remote_object_name="remote/speech_two_ch1.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group="test_group",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

    def test_should_create_evaluation_successfully(self):
        # Given
        expected_eval_id = "test_eval_id"
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": expected_eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 10,
            "status": "ACTIVE",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.create(self.sample_eval_config)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(evaluation.id, expected_eval_id)
        self.assertEqual(evaluation.status, "ACTIVE")

    def test_should_raise_error_on_creation_failure(self):
        # Given
        error_response = Mock(status_code=500)
        error_response.raise_for_status.side_effect = HTTPError("Failed to create evaluation", 500)
        self.mock_api_client.post.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create(self.sample_eval_config)
        self.assertEqual(context.exception.args[0], "Failed to create the evaluation: Failed to create evaluation")

    def test_should_get_evaluation_successfully(self):
        # Given
        eval_id = "test_eval_id"
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 10,
            "status": "active",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")

    def test_should_get_evaluation_with_minimal_data(self):
        # Given
        eval_id = "test_eval_id"
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": None,
            "description": None,
            "batch_size": 10,
            "status": "active",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")
        self.assertIsNone(evaluation.internal_name)
        self.assertIsNone(evaluation.description)

    def test_should_handle_get_evaluation_failure(self):
        # Given
        eval_id = "test_eval_id"
        error_response = Mock(status_code=404)
        error_response.raise_for_status.side_effect = HTTPError("Failed to get evaluation", 404)
        self.mock_api_client.get.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_evaluation(eval_id)
        self.assertEqual(context.exception.args[0], "Failed to get evaluation: Failed to get evaluation")

    def test_should_create_evaluation_files_successfully(self):
        # Given
        eval_id = "test_eval_id"
        expected_response = {"message": "Files created successfully"}
        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        self.service.create_evaluation_files(eval_id, [self.test_audio])

        # Then
        self.mock_api_client.put.assert_called_once()

    def test_should_handle_create_evaluation_files_failure(self):
        # Given
        eval_id = "test_eval_id"
        error_response = Mock(status_code=400)
        error_response.raise_for_status.side_effect = HTTPError("Failed to create evaluation files", 400)
        self.mock_api_client.put.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_evaluation_files(eval_id, [self.test_audio])
        self.assertEqual(context.exception.status_code, 400)

    def test_get_evaluation_list_success(self):
        # Given
        expected_evaluations = [
            {
                "id": "eval1",
                "title": "Evaluation 1",
                "internal_name": "Audio Evaluation",
                "description": "This is a test evaluation",
                "batch_size": 10,
                "status": "ACTIVE",
                "created_time": "2021-01-01T00:00:00Z",
                "updated_time": "2021-01-01T00:00:00Z",
            }
        ]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_evaluations)

        # When
        evaluations = self.service.get_evaluation_list()

        # Then
        self.mock_api_client.get.assert_called_once_with("evaluations")
        self.assertEqual(evaluations[0]["id"], "eval1")
        self.assertEqual(evaluations[0]["title"], "Evaluation 1")
        self.assertEqual(evaluations[0]["internal_name"], "Audio Evaluation")
        self.assertEqual(evaluations[0]["description"], "This is a test evaluation")
        self.assertEqual(evaluations[0]["batch_size"], 10)
        self.assertEqual(evaluations[0]["status"], "ACTIVE")

    def test_get_stats_dict_by_id_success(self):
        # Given
        evaluation_id = "test_evaluation_id"
        expected_stats = [
            {
                "files": [{"name": "file1.wav", "model_tag": "model1", "tags": ["tag1", "tag2"], "type": "A"}],
                "question": {"title": "question1", "order": 1},
                "mean": 0.5,
                "median": 0.5,
                "std": 0.1,
                "sem": 0.05,
                "ci_95": 0.2,
            }
        ]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_stats)

        # When
        stats = self.service.get_stats_dict_by_id(evaluation_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{evaluation_id}/stats")
        self.assertEqual(stats, expected_stats)


if __name__ == "__main__":
    unittest.main()
