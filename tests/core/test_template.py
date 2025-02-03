import unittest
from datetime import datetime

from podonos.core.template import Template, TemplateValidator
from podonos.common.enum import Language, QuestionResponseCategory, QuestionUsageType
from podonos.core.types import TemplateOption, TemplateQuestion


class TestTemplate(unittest.TestCase):
    def test_template_from_api_response(self):
        # Given
        api_response = {
            "id": "template_123",
            "code": "TEST_CODE",
            "title": "Test Template",
            "description": "Test Description",
            "batch_size": 1,
            "language": "en-us",
            "created_time": "2024-03-20T10:00:00Z",
            "updated_time": "2024-03-20T10:30:00Z",
        }

        # When
        template = Template.from_api_response(api_response)

        # Then
        self.assertEqual(template.id, "template_123")
        self.assertEqual(template.code, "TEST_CODE")
        self.assertEqual(template.title, "Test Template")
        self.assertEqual(template.description, "Test Description")
        self.assertEqual(template.batch_size, 1)
        self.assertEqual(template.language, Language.ENGLISH_AMERICAN)
        self.assertIsInstance(template.created_time, datetime)
        self.assertIsInstance(template.updated_time, datetime)

    def test_template_from_api_response_missing_required_field(self):
        # Given
        invalid_response = {
            "id": "template_123",
            "title": "Test Template",
            # Missing required fields
        }

        # When/Then
        with self.assertRaises(ValueError):
            Template.from_api_response(invalid_response)


class TestTemplateOption(unittest.TestCase):
    def test_template_option_to_dict(self):
        # Given
        option = TemplateOption(value="test_value", label_text="Test Label", order=1, id="option_123", label_uri="http://example.com/label")

        # When
        result = option.to_dict()

        # Then
        expected = {"id": "option_123", "value": "test_value", "label_text": "Test Label", "label_uri": "http://example.com/label", "order": 1}
        self.assertEqual(result, expected)

    def test_template_option_to_dict_with_optional_fields(self):
        # Given
        option = TemplateOption(value="test_value")

        # When
        result = option.to_dict()

        # Then
        expected = {"id": None, "value": "test_value", "label_text": None, "label_uri": None, "order": 0}
        self.assertEqual(result, expected)


class TestTemplateQuestion(unittest.TestCase):
    def setUp(self):
        self.sample_options = [TemplateOption(value="1", label_text="Option 1"), TemplateOption(value="2", label_text="Option 2")]

    def test_template_question_to_create_dict(self):
        # Given
        question = TemplateQuestion(
            title="Test Question",
            description="Test Description",
            response_category=QuestionResponseCategory.CHOICE_ONE,
            usage_type=QuestionUsageType.SCORE,
            order=1,
            scale=5,
            has_other=True,
            has_none=False,
            options=self.sample_options,
        )

        # When
        result = question.to_create_dict()

        # Then
        expected = {
            "title": "Test Question",
            "description": "Test Description",
            "response_category": QuestionResponseCategory.CHOICE_ONE.value,
            "usage_type": QuestionUsageType.SCORE.value,
            "scale": 5,
            "order": 1,
            "has_other": True,
            "has_none": False,
        }
        self.assertEqual(result, expected)

    def test_template_question_to_option_bulk_request(self):
        # Given
        question = TemplateQuestion(
            title="Test Question",
            response_category=QuestionResponseCategory.CHOICE_ONE,
            usage_type=QuestionUsageType.SCORE,
            order=1,
            id="question_123",
            options=self.sample_options,
        )

        # When
        result = question.to_option_bulk_request()

        # Then
        self.assertEqual(result["template_question_id"], "question_123")
        self.assertEqual(len(result["options"]), 2)
        self.assertEqual(result["options"][0]["value"], "1")
        self.assertEqual(result["options"][1]["value"], "2")

    def test_template_question_without_options(self):
        # Given
        question = TemplateQuestion(
            title="Test Question", response_category=QuestionResponseCategory.CHOICE_ONE, usage_type=QuestionUsageType.SCORE, order=1
        )

        # When
        result = question.to_option_bulk_request()

        # Then
        self.assertEqual(result["template_question_id"], None)
        self.assertEqual(len(result["options"]), 0)


class TestTemplateValidator(unittest.TestCase):
    def setUp(self):
        self.valid_single_template = {
            "query": [
                {
                    "type": "SCORED",
                    "title": "Audio Quality",
                    "description": "Rate the audio quality",
                    "options": [{"value": "1", "label_text": "Poor"}, {"value": "2", "label_text": "Good"}],
                }
            ],
            "guide": [{"type": "GUIDE", "title": "Evaluation Guide", "description": "How to evaluate", "category": "WARNING"}],
        }

        self.valid_double_template = {
            "query": [{"type": "COMPARISON", "title": "Compare Audio", "description": "Compare two audio samples", "scale": 7}]
        }

    def test_validate_single_stimulus_template(self):
        # When
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(self.valid_single_template, 1)

        # Then
        self.assertEqual(len(guide_questions), 1)
        self.assertEqual(len(core_questions), 1)
        self.assertEqual(guide_questions[0].usage_type, QuestionUsageType.GUIDELINE_WARNING)
        self.assertEqual(core_questions[0].response_category, QuestionResponseCategory.CHOICE_ONE)

    def test_validate_double_stimulus_template(self):
        # When
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(self.valid_double_template, 2)

        # Then
        self.assertEqual(len(guide_questions), 0)
        self.assertEqual(len(core_questions), 1)
        self.assertEqual(core_questions[0].response_category, QuestionResponseCategory.SCALE_LINEAR)

    def test_validate_missing_query(self):
        # Given
        invalid_template = {"guide": []}

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1)
        self.assertIn("must contain a 'query' list", str(context.exception))

    def test_validate_empty_query(self):
        # Given
        invalid_template = {"query": []}

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1)
        self.assertIn("must contain at least one query question", str(context.exception))

    def test_validate_invalid_guide_question_type(self):
        # Given
        invalid_template = {
            "query": [{"type": "SCORED", "title": "Test", "options": [{"value": "1"}]}],
            "guide": [{"type": "SCORED", "title": "Invalid Guide", "options": [{"value": "1"}]}],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1)
        self.assertIn("must be of type GUIDE", str(context.exception))

    def test_validate_comparison_in_single_stimulus(self):
        # Given
        invalid_template = {"query": [{"type": "COMPARISON", "title": "Compare", "scale": 5}]}

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1)
        self.assertIn("not allowed in single stimulus evaluation", str(context.exception))


if __name__ == "__main__":
    unittest.main()
