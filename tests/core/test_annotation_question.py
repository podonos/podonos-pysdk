from typing import Any, Dict

import pytest

from podonos.common.enum import (
    QuestionRelatedModel,
    QuestionResponseCategory,
    QuestionUsageType,
)
from podonos.core.query import TYPE_OF_QUESTION_KEY, AnnotationQuestion


class TestAnnotationQuestion:
    """Unit tests for AnnotationQuestion class."""

    def test_creation_basic(self):
        """Test basic creation with minimal params."""
        q = AnnotationQuestion(question="Describe issues", batch_size=1)
        assert q.question == "Describe issues"
        assert q.question_or_instruction == "Describe issues"
        assert q.batch_size == 1
        assert q.related_model is None
        assert q.type == "ANNOTATION"

    def test_creation_with_all_params(self):
        """Test creation with all parameters."""
        q = AnnotationQuestion(
            question="Describe issues",
            batch_size=2,
            related_model=QuestionRelatedModel.MODEL_A,
            description="Please describe any issues you noticed",
            order=5,
        )
        assert q.question == "Describe issues"
        assert q.question_or_instruction == "Describe issues"
        assert q.batch_size == 2
        assert q.related_model == QuestionRelatedModel.MODEL_A
        assert q.description == "Please describe any issues you noticed"
        assert q.order == 5

    def test_empty_question_raises(self):
        """Test that empty question raises ValueError."""
        q = AnnotationQuestion(question="", batch_size=1)
        with pytest.raises(ValueError, match="must have a 'question' or 'instruction'"):
            q.validate()

    def test_whitespace_question_raises(self):
        """Test that whitespace-only question raises ValueError."""
        q = AnnotationQuestion(question="   ", batch_size=1)
        with pytest.raises(ValueError, match="cannot be empty"):
            q.validate()

    def test_single_stimulus_allows_none(self):
        """Test single-stimulus allows None related_model."""
        q = AnnotationQuestion(question="Test", batch_size=1, related_model=None)
        q.validate()  # Should not raise

    def test_single_stimulus_allows_all(self):
        """Test single-stimulus allows ALL related_model."""
        q = AnnotationQuestion(
            question="Test", batch_size=1, related_model=QuestionRelatedModel.ALL
        )
        q.validate()  # Should not raise

    def test_single_stimulus_rejects_model_a(self):
        """Test single-stimulus rejects MODEL_A."""
        q = AnnotationQuestion(
            question="Test", batch_size=1, related_model=QuestionRelatedModel.MODEL_A
        )
        with pytest.raises(ValueError, match="must be ALL"):
            q.validate()

    def test_single_stimulus_rejects_model_b(self):
        """Test single-stimulus rejects MODEL_B."""
        q = AnnotationQuestion(
            question="Test", batch_size=1, related_model=QuestionRelatedModel.MODEL_B
        )
        with pytest.raises(ValueError, match="must be ALL"):
            q.validate()

    def test_double_stimulus_requires_model(self):
        """Test double-stimulus requires MODEL_A or MODEL_B."""
        q = AnnotationQuestion(question="Test", batch_size=2, related_model=None)
        with pytest.raises(ValueError, match="required for multi-stimulus"):
            q.validate()

    def test_double_stimulus_rejects_all(self):
        """Test double-stimulus rejects ALL."""
        q = AnnotationQuestion(
            question="Test", batch_size=2, related_model=QuestionRelatedModel.ALL
        )
        with pytest.raises(ValueError, match="cannot be ALL"):
            q.validate()

    def test_double_stimulus_accepts_model_a(self):
        """Test double-stimulus accepts MODEL_A."""
        q = AnnotationQuestion(
            question="Test", batch_size=2, related_model=QuestionRelatedModel.MODEL_A
        )
        q.validate()  # Should not raise

    def test_double_stimulus_accepts_model_b(self):
        """Test double-stimulus accepts MODEL_B."""
        q = AnnotationQuestion(
            question="Test", batch_size=2, related_model=QuestionRelatedModel.MODEL_B
        )
        q.validate()  # Should not raise

    def test_triple_stimulus_accepts_model_a(self):
        """Test triple-stimulus (batch_size=3) accepts MODEL_A."""
        q = AnnotationQuestion(
            question="Test", batch_size=3, related_model=QuestionRelatedModel.MODEL_A
        )
        q.validate()  # Should not raise

    def test_triple_stimulus_accepts_model_b(self):
        """Test triple-stimulus (batch_size=3) accepts MODEL_B."""
        q = AnnotationQuestion(
            question="Test", batch_size=3, related_model=QuestionRelatedModel.MODEL_B
        )
        q.validate()  # Should not raise

    def test_triple_stimulus_rejects_all(self):
        """Test triple-stimulus rejects ALL."""
        q = AnnotationQuestion(
            question="Test", batch_size=3, related_model=QuestionRelatedModel.ALL
        )
        with pytest.raises(ValueError, match="cannot be ALL"):
            q.validate()

    def test_triple_stimulus_rejects_none(self):
        """Test triple-stimulus rejects None."""
        q = AnnotationQuestion(question="Test", batch_size=3, related_model=None)
        with pytest.raises(ValueError, match="required for multi-stimulus"):
            q.validate()

    def test_to_template_question(self):
        """Test conversion to TemplateQuestion."""
        q = AnnotationQuestion(
            question="Describe issues",
            batch_size=1,
            related_model=QuestionRelatedModel.ALL,
            description="Optional description",
            order=5,
        )
        tq = q.to_template_question()

        assert tq.title == "Describe issues"
        assert tq.response_category == QuestionResponseCategory.ANNOTATION
        assert tq.usage_type == QuestionUsageType.ANNOTATION
        assert tq.related_model == QuestionRelatedModel.ALL
        assert tq.description == "Optional description"
        assert tq.order == 5

    def test_to_template_question_defaults_to_all_for_single(self):
        """Test that None related_model defaults to ALL for single-stimulus."""
        q = AnnotationQuestion(question="Test", batch_size=1, related_model=None)
        tq = q.to_template_question()
        assert tq.related_model == QuestionRelatedModel.ALL

    def test_to_template_question_preserves_model_for_double(self):
        """Test that related_model is preserved for double-stimulus."""
        q = AnnotationQuestion(
            question="Test", batch_size=2, related_model=QuestionRelatedModel.MODEL_A
        )
        tq = q.to_template_question()
        assert tq.related_model == QuestionRelatedModel.MODEL_A

    def test_from_dict_basic(self):
        """Test creation from dictionary."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Describe issues",
            "related_model": "MODEL_A",
            "description": "Details",
            "order": 3,
        }
        q = AnnotationQuestion.from_dict(data, batch_size=2)

        assert q.question == "Describe issues"
        assert q.question_or_instruction == "Describe issues"
        assert q.related_model == QuestionRelatedModel.MODEL_A
        assert q.description == "Details"
        assert q.order == 3
        assert q.batch_size == 2

    def test_from_dict_minimal(self):
        """Test creation from dictionary with minimal fields."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Describe issues",
        }
        q = AnnotationQuestion.from_dict(data, batch_size=1)

        assert q.question == "Describe issues"
        assert q.question_or_instruction == "Describe issues"
        assert q.related_model is None
        assert q.description is None
        assert q.order == 0

    def test_from_dict_with_all_related_model(self):
        """Test from_dict with ALL related_model."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Test",
            "related_model": "ALL",
        }
        q = AnnotationQuestion.from_dict(data, batch_size=1)
        assert q.related_model == QuestionRelatedModel.ALL

    def test_from_dict_with_model_b(self):
        """Test from_dict with MODEL_B related_model."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Test",
            "related_model": "MODEL_B",
        }
        q = AnnotationQuestion.from_dict(data, batch_size=2)
        assert q.related_model == QuestionRelatedModel.MODEL_B

    def test_from_dict_invalid_related_model(self):
        """Test from_dict with invalid related_model."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Test",
            "related_model": "INVALID",
        }
        with pytest.raises(ValueError, match="Invalid related_model"):
            AnnotationQuestion.from_dict(data, batch_size=2)

    def test_from_dict_no_related_model(self):
        """Test from_dict without related_model."""
        data: Dict[TYPE_OF_QUESTION_KEY, Any] = {
            "type": "ANNOTATION",
            "question": "Test",
        }
        q = AnnotationQuestion.from_dict(data, batch_size=1)
        assert q.related_model is None

    def test_deprecated_title_parameter(self):
        """Test that deprecated title parameter still works with warning."""
        import warnings as w

        with w.catch_warnings(record=True) as caught_warnings:
            w.simplefilter("always")
            q = AnnotationQuestion(title="Test Question", batch_size=1)
            assert q.question == "Test Question"
            assert q.question_or_instruction == "Test Question"
            assert len(caught_warnings) == 1
            assert "deprecated" in str(caught_warnings[0].message).lower()

    def test_deprecated_title_property_access(self):
        """Test that accessing title property emits deprecation warning."""
        import warnings as w

        q = AnnotationQuestion(question="Test Question", batch_size=1)
        with w.catch_warnings(record=True) as caught_warnings:
            w.simplefilter("always")
            _ = q.title  # Access deprecated property
            assert len(caught_warnings) == 1
            assert "deprecated" in str(caught_warnings[0].message).lower()
