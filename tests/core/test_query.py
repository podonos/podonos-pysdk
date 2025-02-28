from typing import Any, Dict
import unittest
from podonos.core.query import TYPE_OF_QUESTION_KEY, Question, ScoredQuestion, NonScoredQuestion, ComparisonQuestion, Instruction, Option
from podonos.common.enum import InstructionCategory, QuestionRelatedModel
from podonos.core.types import QuestionMetadataColumn, QuestionMetadataLinearScale, QuestionMetadataPosition


class TestQuery(unittest.TestCase):
    def test_scored_question(self):
        # Given
        title = "Rate your experience"
        description = "Please rate your overall experience"
        options = [Option("1", "Poor"), Option("2", "Fair"), Option("3", "Good")]
        batch_size = 1
        # When
        question = ScoredQuestion(title, options, QuestionRelatedModel.ALL, batch_size, description)
        template = question.to_template_question()

        # Then
        self.assertEqual(question.title, title)
        self.assertEqual(question.description, description)
        self.assertEqual(question.type, "SCORED")
        self.assertEqual(len(question.options), 3)
        self.assertEqual(template.title, title)
        self.assertEqual(len(template.options), 3)

    def test_non_scored_question(self):
        # Given
        title = "Select your interests"
        description = "Choose all that apply"
        options = [Option("reading", "Reading"), Option("sports", "Sports")]
        allow_multiple = True
        batch_size = 1
        related_model = QuestionRelatedModel.ALL

        # When
        question = NonScoredQuestion(
            question=title,
            options=options,
            description=description,
            allow_multiple=allow_multiple,
            has_other=True,
            related_model=related_model,
            batch_size=batch_size,
        )
        template = question.to_template_question()

        # Then
        self.assertEqual(question.title, title)
        self.assertEqual(question.type, "NON_SCORED")
        self.assertTrue(question.allow_multiple)
        self.assertTrue(question.has_other)
        self.assertEqual(len(template.options), 2)

    def test_comparison_question(self):
        # Given
        title = "Compare importance"
        meta_data = QuestionMetadataColumn(
            linear_scale=QuestionMetadataLinearScale(
                title="Importance",
                label_text=QuestionMetadataPosition(left="Not important", right="Very important"),
            )
        )
        description = "Rate from 1-7"
        scale = 7
        batch_size = 1
        related_model = QuestionRelatedModel.ALL

        # When
        question = ComparisonQuestion(title, meta_data, related_model, batch_size, scale, description)
        template = question.to_template_question()

        # Then
        self.assertEqual(question.title, title)
        self.assertEqual(question.type, "COMPARISON")
        self.assertEqual(question.scale, scale)
        self.assertEqual(template.scale, scale)

    def test_guide_question(self):
        # Given
        title = "Important guideline"
        description = "Follow this guideline"
        category = InstructionCategory.WARNING
        batch_size = 1

        # When
        question = Instruction(title, category, batch_size, description)
        template = question.to_template_question()

        # Then
        self.assertEqual(question.title, title)
        self.assertEqual(question.type, "INSTRUCTION")
        self.assertEqual(question.category, InstructionCategory.WARNING)

    def test_invalid_scored_question(self):
        # Given
        title = "Invalid question"
        options = []  # Empty options
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError):
            question = ScoredQuestion(title, options, QuestionRelatedModel.ALL, batch_size)
            question.validate()

    def test_question_from_dict(self):
        # Given
        question_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "question": "Test Question",
            "type": "SCORED",
            "description": "Test Description",
            "options": [{"label_text": "Option 1"}, {"label_text": "Option 2"}],
        }
        batch_size = 1

        # When
        question = Question.from_dict(question_data, batch_size)

        # Then
        assert isinstance(question, ScoredQuestion)
        self.assertEqual(question.title, "Test Question")
        self.assertEqual(len(question.options), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
