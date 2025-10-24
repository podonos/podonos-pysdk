from typing import Any, Dict, List
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
        self.assertEqual(question.title, template.title)
        self.assertEqual(question.type, "INSTRUCTION")
        self.assertEqual(question.category, InstructionCategory.WARNING)

    def test_invalid_scored_question(self):
        # Given
        title = "Invalid question"
        options: List[Option] = []  # Empty options
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

    def test_instruction_with_reference_files(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "description": "Follow the guide",
            "reference_files": [{"path": "/path/to/file.wav", "type": "audio"}],
        }
        batch_size = 1

        # When
        instruction = Instruction.from_dict(instruction_data, batch_size)

        # Then
        assert isinstance(instruction, Instruction)
        self.assertEqual(instruction.title, "Listen to the audio")
        self.assertEqual(instruction.category, InstructionCategory.WARNING)
        self.assertIsNotNone(instruction.reference_files)
        assert instruction.reference_files is not None
        self.assertEqual(len(instruction.reference_files), 1)
        self.assertEqual(instruction.reference_files[0]["path"], "/path/to/file.wav")
        self.assertEqual(instruction.reference_files[0]["type"], "audio")

    def test_instruction_with_reference_file_should_fail(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "reference_file": "/path/to/file.wav",  # Invalid: should use reference_files
        }
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError) as context:
            Instruction.from_dict(instruction_data, batch_size)
        self.assertIn("reference_file' field is not allowed for instruction questions", str(context.exception))

    def test_instruction_with_non_list_reference_files_should_fail(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "reference_files": "not a list",  # Invalid: should be a list
        }
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError) as context:
            Instruction.from_dict(instruction_data, batch_size)
        self.assertIn("Reference files must be a List", str(context.exception))

    def test_instruction_with_non_dict_reference_file_should_fail(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "reference_files": ["not a dict"],  # Invalid: should be a list of dicts
        }
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError) as context:
            Instruction.from_dict(instruction_data, batch_size)
        self.assertIn("Reference files must be a List of Dict", str(context.exception))

    def test_instruction_with_missing_path_in_reference_file_should_fail(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "reference_files": [{"type": "audio"}],  # Missing 'path' field
        }
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError) as context:
            Instruction.from_dict(instruction_data, batch_size)
        self.assertIn("Reference files must have 'path' and 'type' fields", str(context.exception))

    def test_instruction_with_missing_type_in_reference_file_should_fail(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to the audio",
            "type": "WARNING",
            "reference_files": [{"path": "/path/to/file.wav"}],  # Missing 'type' field
        }
        batch_size = 1

        # When/Then
        with self.assertRaises(ValueError) as context:
            Instruction.from_dict(instruction_data, batch_size)
        self.assertIn("Reference files must have 'path' and 'type' fields", str(context.exception))

    def test_instruction_with_multiple_reference_files(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Listen to multiple audios",
            "type": "DO",
            "reference_files": [
                {"path": "/path/to/file1.wav", "type": "audio"},
                {"path": "/path/to/file2.wav", "type": "reference"},
            ],
        }
        batch_size = 1

        # When
        instruction = Instruction.from_dict(instruction_data, batch_size)

        # Then
        assert isinstance(instruction, Instruction)
        assert instruction.reference_files is not None
        self.assertEqual(len(instruction.reference_files), 2)
        self.assertEqual(instruction.reference_files[0]["path"], "/path/to/file1.wav")
        self.assertEqual(instruction.reference_files[1]["type"], "reference")

    def test_instruction_without_reference_files(self):
        # Given
        instruction_data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "instruction": "Simple instruction",
            "type": "DONT",
        }
        batch_size = 1

        # When
        instruction = Instruction.from_dict(instruction_data, batch_size)

        # Then
        assert isinstance(instruction, Instruction)
        self.assertIsNone(instruction.reference_files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
