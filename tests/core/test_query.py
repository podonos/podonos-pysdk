import unittest
from podonos.core.query import Question, ScoredQuestion, NonScoredQuestion, ComparisonQuestion, GuideQuestion, Option
from podonos.common.enum import GuideCategory


class TestQuery(unittest.TestCase):
    def test_scored_question(self):
        # Given
        title = "Rate your experience"
        description = "Please rate your overall experience"
        options = [Option("1", "Poor"), Option("2", "Fair"), Option("3", "Good")]

        # When
        question = ScoredQuestion(title, options, description)
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

        # When
        question = NonScoredQuestion(title=title, options=options, description=description, allow_multiple=allow_multiple, has_other=True)
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
        description = "Rate from 1-7"
        scale = 7

        # When
        question = ComparisonQuestion(title, scale, description)
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
        category = GuideCategory.WARNING

        # When
        question = GuideQuestion(title, category, description)
        template = question.to_template_question()

        # Then
        self.assertEqual(question.title, title)
        self.assertEqual(question.type, "GUIDE")
        self.assertEqual(question.category, GuideCategory.WARNING)

    def test_invalid_scored_question(self):
        # Given
        title = "Invalid question"
        options = []  # Empty options

        # When/Then
        with self.assertRaises(ValueError):
            question = ScoredQuestion(title, options)
            question.validate()

    def test_question_from_dict(self):
        # Given
        question_data = {
            "title": "Test Question",
            "type": "SCORED",
            "description": "Test Description",
            "options": [{"value": "1", "label_text": "Option 1"}, {"value": "2", "label_text": "Option 2"}],
        }

        # When
        question = Question.from_dict(question_data)

        # Then
        assert isinstance(question, ScoredQuestion)
        self.assertEqual(question.title, "Test Question")
        self.assertEqual(len(question.options), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
