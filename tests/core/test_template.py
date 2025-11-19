import pytest
from typing import Any, Dict
import unittest
from datetime import datetime

from podonos.core.template import TYPE_OF_TEMPLATE_KEY, Template, TemplateValidator
from podonos.common.enum import Language, QuestionResponseCategory, QuestionUsageType, EvalType
from podonos.core.types import QuestionMetadataColumn, QuestionMetadataLinearScale, QuestionMetadataPosition, TemplateOption, TemplateQuestion
from tests.core.test_audio import TESTDATA_SPEECH_CH1_MP3


class TestTemplate(unittest.TestCase):
    def test_template_from_api_response(self):
        # Given
        api_response = {
            "id": "template_123",
            "code": "TEST_CODE",
            "title": "Test Template",
            "description": "Test Description",
            "eval_type": "CUSTOM",
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
            meta_data=QuestionMetadataColumn(
                linear_scale=QuestionMetadataLinearScale(
                    title="Preference",
                    label_text=QuestionMetadataPosition(left="Better", right="Better"),
                )
            ),
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
            "meta_data": {
                "linear_scale": {
                    "title": "Preference",
                    "label_text": {"left": "Better", "right": "Better"},
                }
            },
        }
        self.assertEqual(result["title"], expected["title"])
        self.assertEqual(result["description"], expected["description"])
        self.assertEqual(result["response_category"], expected["response_category"])
        self.assertEqual(result["usage_type"], expected["usage_type"])
        self.assertEqual(result["scale"], expected["scale"])
        self.assertEqual(result["order"], expected["order"])
        self.assertEqual(result["has_other"], expected["has_other"])
        self.assertEqual(result["has_none"], expected["has_none"])

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
        self.valid_single_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Audio Quality",
                    "description": "Rate the audio quality",
                    "options": [{"value": "1", "label_text": "Poor"}, {"value": "2", "label_text": "Good"}],
                }
            ],
            "instructions": [{"type": "WARNING", "instruction": "Evaluation Guide", "description": "How to evaluate"}],
        }

        self.valid_double_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare Audio",
                    "description": "Compare two audio samples",
                    "scale": 5,
                    "anchor_label": {"label_text": {"left": "Option A", "right": "Option B"}},
                }
            ]
        }

        self.valid_comparison_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare A and B",
                    "description": "Compare two audio samples",
                    "scale": 5,
                    "anchor_label": {"label_text": {"left": "Option A", "right": "Option B"}},
                }
            ]
        }

    def test_validate_single_stimulus_template(self):
        # When
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(
            self.valid_single_template, 1, eval_type=EvalType.CUSTOM_SINGLE
        )

        # Then
        self.assertEqual(len(guide_questions), 1)
        self.assertEqual(len(core_questions), 1)
        self.assertEqual(guide_questions[0].usage_type, QuestionUsageType.GUIDELINE_WARNING)
        self.assertEqual(core_questions[0].response_category, QuestionResponseCategory.CHOICE_ONE)

    def test_validate_double_stimulus_template(self):
        # When
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(
            self.valid_double_template, 2, eval_type=EvalType.CUSTOM_DOUBLE
        )

        # Then
        self.assertEqual(len(guide_questions), 0)
        self.assertEqual(len(core_questions), 1)
        self.assertEqual(core_questions[0].response_category, QuestionResponseCategory.SCALE_LINEAR)

    def test_validate_missing_query(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {"instructions": []}

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("must contain a 'questions' list", str(context.exception))

    def test_validate_empty_query(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {"questions": []}

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("must contain between 1 and 9 questions", str(context.exception))

    def test_validate_invalid_instruction_question_type(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [{"type": "SCORED", "question": "Test", "options": [{"label_text": "Option 1"}]}],
            "instructions": [{"type": "SCORED", "question": "Invalid Guide", "options": [{"label_text": "Option 1"}]}],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertEqual("Question in instructions section must be one of the following types: Instruction, got SCORED", str(context.exception))

    def test_validate_comparison_in_single_stimulus(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare",
                    "scale": 5,
                    "anchor_label": {"title": "Preference", "label_text": {"left": "Better", "right": "Better"}},
                }
            ],
        }
        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("not allowed in single stimulus evaluation", str(context.exception))

    def test_validate_reference_file_with_instruction_should_fail(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [{"type": "SCORED", "question": "Test", "options": [{"label_text": "Option 1"}]}],
            "instructions": [
                {"type": "WARNING", "instruction": "Evaluation Guide", "description": "How to evaluate", "reference_file": TESTDATA_SPEECH_CH1_MP3}
            ],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("reference_file' field is not allowed for instruction questions", str(context.exception))

    def test_validate_reference_files_success(self):
        # Given
        valid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [{"type": "SCORED", "question": "Test", "options": [{"label_text": "Option 1"}]}],
            "instructions": [
                {
                    "type": "WARNING",
                    "instruction": "Evaluation Guide",
                    "description": "How to evaluate",
                    "reference_files": [{"path": TESTDATA_SPEECH_CH1_MP3, "type": "audio"}],
                }
            ],
        }

        # When
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(valid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)

        # Then
        self.assertEqual(len(guide_questions), 1)
        self.assertEqual(len(core_questions), 1)
        self.assertEqual(guide_questions[0].usage_type, QuestionUsageType.GUIDELINE_WARNING)
        self.assertIsNotNone(guide_questions[0].reference_files)
        assert guide_questions[0].reference_files is not None
        self.assertEqual(len(guide_questions[0].reference_files), 1)

    def test_validate_reference_files_not_found(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [{"type": "SCORED", "question": "Test", "options": [{"label_text": "Option 1"}]}],
            "instructions": [
                {
                    "type": "DO",
                    "instruction": "Evaluation Guide",
                    "description": "How to evaluate",
                    "reference_files": [{"path": "nonexistent.wav", "type": "audio"}],
                }
            ],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("Reference file not found", str(context.exception))

    def test_validate_reference_files_invalid_type(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [{"type": "SCORED", "question": "Test", "options": [{"label_text": "Option 1"}]}],
            "instructions": [
                {
                    "type": "DO",
                    "instruction": "Evaluation Guide",
                    "description": "How to evaluate",
                    "reference_files": [{"path": TESTDATA_SPEECH_CH1_MP3, "type": "invalid_type"}],
                }
            ],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn("Reference file type must be one of the following: reference, target, audio", str(context.exception))

    def test_validate_comparison_question_success(self):
        # When
        result = TemplateValidator.validate_and_create_questions(self.valid_comparison_template, 2, eval_type=EvalType.CUSTOM_DOUBLE)

        # Then
        self.assertEqual(len(result[0]), 0)
        self.assertEqual(len(result[1]), 1)

    def test_template_validator_ranking_allows_instruction_and_comparison(self):
        data: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "instructions": [
                {"type": "DO", "instruction": "Follow the guide"},
            ],
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "A vs B",
                    "anchor_label": {"label_text": {"left": "Left", "right": "Right"}},
                }
            ],
        }
        instructions, questions = TemplateValidator.validate_and_create_questions(data, batch_size=2, eval_type=EvalType.RANKING)
        assert len(instructions) == 1
        assert len(questions) == 1

    def test_template_validator_ranking_rejects_scored(self):
        data: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "instructions": [],
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Rate",
                    "options": [{"label_text": "1"}],
                }
            ],
        }
        with pytest.raises(Exception):
            TemplateValidator.validate_and_create_questions(data, batch_size=2, eval_type=EvalType.RANKING)

    def test_validate_comparison_question_missing_anchor_label(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare A and B",
                    "scale": 5,
                }
            ]
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn(
            "COMPARISON question must have 'anchor_label' in the format: {'anchor_label': {'title': optional string, 'label_text': {'left': string, 'right': string}}}",
            str(context.exception),
        )

    def test_validate_comparison_question_invalid_anchor_label_format(self):
        # Given
        invalid_template: Dict[TYPE_OF_TEMPLATE_KEY, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare A and B",
                    "anchor_label": {
                        "label_text": {
                            "left": "Option A"
                            # Missing right text
                        }
                    },
                }
            ]
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            TemplateValidator.validate_and_create_questions(invalid_template, 1, eval_type=EvalType.CUSTOM_SINGLE)
        self.assertIn(
            "COMPARISON question must have 'anchor_label' in the format: {'anchor_label': {'title': optional string, 'label_text': {'left': string, 'right': string}}}",
            str(context.exception),
        )


if __name__ == "__main__":
    unittest.main()
