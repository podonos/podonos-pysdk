import unittest
from unittest.mock import Mock, patch
from podonos.service.ai_evaluation_service import AIEvaluationService
from podonos.core.api import APIClient
from podonos.common.enum import AIEvalType
from podonos.common.exception import HTTPError


class TestAIEvaluationService(unittest.TestCase):
    def setUp(self):
        self.mock_api_client = Mock(spec=APIClient)
        self.service = AIEvaluationService(self.mock_api_client)
        self.evaluation_id = "test_evaluation_id"
        self.ai_eval_type = AIEvalType.ASR

    def test_create_ai_evaluation_success(self):
        # Given
        self.mock_api_client.post.return_value = Mock(status_code=200)

        # When
        self.service.create(self.evaluation_id, self.ai_eval_type)

        # Then
        self.mock_api_client.post.assert_called_once_with(
            "ai-evaluation-requests", data={"evaluation_id": self.evaluation_id, "type": self.ai_eval_type.value}
        )

    def test_create_ai_evaluation_failure(self):
        # Given
        self.mock_api_client.post.return_value = Mock(status_code=400, raise_for_status=Mock(side_effect=HTTPError("Failed to create AI evaluation")))

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create(self.evaluation_id, self.ai_eval_type)

        # Assert the error message
        self.assertIn("Failed to create AI evaluation", str(context.exception))

        # Then
        self.mock_api_client.post.assert_called_once_with(
            "ai-evaluation-requests", data={"evaluation_id": self.evaluation_id, "type": self.ai_eval_type.value}
        )


if __name__ == "__main__":
    unittest.main()
