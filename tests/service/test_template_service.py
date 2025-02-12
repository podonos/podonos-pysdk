import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from podonos.core.api import APIClient
from podonos.core.template import Template
from podonos.core.types import TemplateOption, TemplateQuestion
from podonos.common.enum import QuestionResponseCategory, QuestionUsageType
from podonos.service.template_service import TemplateService


class TestTemplateService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = TemplateService(self.mock_api_client)
        self.template_id = "test_template_id"

        # Mock template data with all required fields
        current_time = datetime.now(timezone.utc)
        self.mock_template_data = {
            "id": self.template_id,
            "code": "TEST_CODE",
            "title": "Test Template",
            "description": "Test Description",
            "batch_size": 1,
            "language": "en-us",  # Language enum value
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
            "questions": [],  # Optional field
        }

    def test_should_get_template_by_code_successfully(self):
        # Given
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: self.mock_template_data)

        # When
        template = self.service.get_template_by_code(self.template_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"templates/one?code={self.template_id}")
        self.assertIsInstance(template, Template)
        self.assertEqual(template.id, self.template_id)

    def test_should_create_template_questions_successfully(self):
        # Given
        evaluation_id = "test_eval_id"
        template_questions = [
            TemplateQuestion(title="Test Question", response_category=QuestionResponseCategory.CHOICE_ONE, usage_type=QuestionUsageType.SCORE)
        ]

        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: [{"id": "question_id"}])

        # When
        response = self.service.create_template_questions_by_evaluation_id_and_questions(evaluation_id, template_questions)

        # Then
        self.mock_api_client.put.assert_called_once_with(
            "template-questions/bulk", data={"evaluation_id": evaluation_id, "questions": [q.to_create_dict() for q in template_questions]}
        )
        self.assertIn("id", response[0])

    def test_should_create_template_options_successfully(self):
        # Given
        question_id = "test_question_id"
        template_options = [TemplateOption(value="Option 1"), TemplateOption(value="Option 2")]

        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: [{"id": "option_id"}])

        # When
        response = self.service.create_template_options_by_question_id_and_options(question_id, template_options)

        # Then
        self.mock_api_client.put.assert_called_once_with(
            "template-options/bulk", data={"template_question_id": question_id, "options": [opt.to_dict() for opt in template_options]}
        )
        self.assertIn("id", response[0])


if __name__ == "__main__":
    unittest.main()
