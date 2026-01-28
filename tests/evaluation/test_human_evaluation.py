import unittest
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import Mock
from uuid import uuid4

from podonos.common.enum import CustomType, EvalType, Language
from podonos.core.api import APIClient
from podonos.core.template import Template
from podonos.entity.evaluation import EvaluationEntity
from podonos.evaluation.human_evaluation import HumanEvaluation


def make_evaluation_entity(eval_id: str) -> EvaluationEntity:
    """Helper to create a valid EvaluationEntity for testing"""
    current_time = datetime.now(timezone.utc)
    return EvaluationEntity.from_dict(
        {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 1,
            "status": "ACTIVE",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
    )


class TestHumanEvaluation(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.mock_evaluation_service = Mock()
        self.mock_template_service = Mock()

        # Mock API responses that Evaluator will use internally
        eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        mock_eval_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 1,
            "status": "ACTIVE",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        mock_response = Mock()
        mock_response.json.return_value = mock_eval_response
        mock_response.status_code = 200
        self.mock_api_client.post.return_value = mock_response

        self.human_eval = HumanEvaluation(
            self.mock_api_client,
            self.mock_evaluation_service,
            self.mock_template_service,
        )

    def test_create_nmos_evaluation_successfully(self):
        """Test creating NMOS evaluation"""
        # Given/When
        evaluator = self.human_eval.create(
            name="Test NMOS",
            type=EvalType.NMOS.value,
            lan=Language.ENGLISH_AMERICAN.value,
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.NMOS)  # type: ignore
        self.assertIn(EvalType.NMOS, evaluator._supported_eval_types)  # type: ignore

    def test_create_custom_single_evaluation_successfully(self):
        """Test creating CUSTOM_SINGLE evaluation"""
        # Given/When
        evaluator = self.human_eval.create(
            name="Test Custom Single",
            type=EvalType.CUSTOM_SINGLE.value,
            lan=Language.ENGLISH_AMERICAN.value,
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CUSTOM_SINGLE)  # type: ignore
        self.assertIn(EvalType.CUSTOM_SINGLE, evaluator._supported_eval_types)  # type: ignore

    def test_create_custom_double_evaluation_successfully(self):
        """Test creating CUSTOM_DOUBLE evaluation"""
        # Given/When
        evaluator = self.human_eval.create(
            name="Test Custom Double",
            type=EvalType.CUSTOM_DOUBLE.value,
            lan=Language.ENGLISH_AMERICAN.value,
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CUSTOM_DOUBLE)  # type: ignore
        self.assertIn(EvalType.CUSTOM_DOUBLE, evaluator._supported_eval_types)  # type: ignore

    def test_create_with_invalid_type_raises_error(self):
        """Test creating evaluation with invalid type raises ValueError"""
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.human_eval.create(type="INVALID_TYPE")
        self.assertIn("Not supported evaluation types", str(context.exception))

    def test_create_from_template_with_nmos_template(self):
        """Test creating from NMOS template"""
        # Given
        template = Template(
            id="template_id",
            code="NMOS_TEMPLATE",
            title="NMOS Template",
            description="Test NMOS template",
            language=Language.ENGLISH_AMERICAN,
            batch_size=1,
            evaluation_type="SPEECH_NMOS",
            created_time=None,
            updated_time=None,
        )
        eval_id = str(uuid4())
        self.mock_template_service.get_template_by_code.return_value = template
        self.mock_evaluation_service.create.return_value = make_evaluation_entity(
            eval_id
        )

        # When
        evaluator = self.human_eval.create_from_template(
            name="Test from Template", template_id="NMOS_TEMPLATE", num_eval=10
        )

        # Then
        self.assertIsNotNone(evaluator)
        # Note: create_from_template uses batch_size to determine type, not the template's evaluation_type
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CUSTOM_SINGLE)  # type: ignore
        self.mock_template_service.get_template_by_code.assert_called_once_with(
            "NMOS_TEMPLATE"
        )

    def test_create_from_template_with_custom_template(self):
        """Test creating from CUSTOM template"""
        # Given
        template = Template(
            id="template_id",
            code="CUSTOM_TEMPLATE",
            title="Custom Template",
            description="Test custom template",
            language=Language.ENGLISH_AMERICAN,
            batch_size=1,
            evaluation_type="CUSTOM",
            created_time=None,
            updated_time=None,
        )
        eval_id = str(uuid4())
        self.mock_template_service.get_template_by_code.return_value = template
        self.mock_evaluation_service.create.return_value = make_evaluation_entity(
            eval_id
        )

        # When
        evaluator = self.human_eval.create_from_template(
            name="Test Custom", template_id="CUSTOM_TEMPLATE", num_eval=5
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CUSTOM_SINGLE)  # type: ignore

    def test_create_from_template_ranking_builds_ranking_evaluator(self):
        """Test creating from RANKING template"""
        # Given
        template = Template(
            id="template_id",
            code="RANKING_TEMPLATE",
            title="Ranking Template",
            description="Test ranking template",
            language=Language.ENGLISH_AMERICAN,
            batch_size=2,
            evaluation_type="SPEECH_RANKING",
            created_time=None,
            updated_time=None,
        )
        eval_id = str(uuid4())
        self.mock_template_service.get_template_by_code.return_value = template
        self.mock_evaluation_service.create.return_value = make_evaluation_entity(
            eval_id
        )

        # When
        evaluator = self.human_eval.create_from_template(
            name="Test Ranking", template_id="RANKING_TEMPLATE", num_eval=3
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.RANKING)  # type: ignore
        self.assertEqual(evaluator._supported_eval_types, [EvalType.RANKING])  # type: ignore

    def test_create_from_template_with_cmos_template(self):
        """Test creating from CMOS template"""
        # Given
        template = Template(
            id="template_id",
            code="CMOS_TEMPLATE",
            title="CMOS Template",
            description="Test CMOS template",
            language=Language.ENGLISH_AMERICAN,
            batch_size=2,
            evaluation_type="SPEECH_CMOS",
            created_time=None,
            updated_time=None,
        )
        eval_id = str(uuid4())
        self.mock_template_service.get_template_by_code.return_value = template
        self.mock_evaluation_service.create.return_value = make_evaluation_entity(
            eval_id
        )

        # When
        evaluator = self.human_eval.create_from_template(
            name="Test CMOS", template_id="CMOS_TEMPLATE", num_eval=5
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CMOS)  # type: ignore
        self.assertIn(EvalType.CMOS, evaluator._supported_eval_types)  # type: ignore
        self.mock_template_service.get_template_by_code.assert_called_once_with(
            "CMOS_TEMPLATE"
        )

    def test_create_from_template_with_no_batch_size_raises_error(self):
        """Test creating from template with no batch_size raises ValueError"""
        # Given
        template = Template(
            id="template_id",
            code="INVALID_TEMPLATE",
            title="Invalid Template",
            description="Template without batch size",
            language=Language.ENGLISH_AMERICAN,
            batch_size=None,
            evaluation_type=None,
            created_time=None,
            updated_time=None,
        )
        self.mock_template_service.get_template_by_code.return_value = template

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.human_eval.create_from_template(
                name="Test Invalid", template_id="INVALID_TEMPLATE", num_eval=5
            )
        self.assertIn("has no batch size", str(context.exception))

    def test_create_from_template_json_with_invalid_custom_type_raises_error(self):
        """Test creating from template JSON with invalid custom_type raises ValueError"""
        # Given
        template_json: Dict[str, Any] = {"questions": [], "instructions": []}

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.human_eval.create_from_template_json(
                json=template_json, name="Test Invalid", custom_type="INVALID"
            )  # type: ignore
        self.assertIn(
            "custom_type must be one of SINGLE, DOUBLE, SINGLE_REF, RANKING",
            str(context.exception),
        )

    def test_create_from_template_json_mutual_exclusivity_error(self):
        """Test that use_annotation=True + explicit AnnotationQuestion raises ValueError"""
        # Given - template with both use_annotation and annotations
        template_json: Dict[str, Any] = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Rate quality",
                    "options": [{"label_text": "Poor"}, {"label_text": "Excellent"}],
                }
            ],
            "annotations": [
                {
                    "type": "ANNOTATION",
                    "question": "Describe issues",
                    "related_model": "ALL",
                }
            ],
        }

        # When/Then
        with self.assertRaises(ValueError) as context:
            self.human_eval.create_from_template_json(
                json=template_json,
                name="Test Mutual Exclusivity",
                use_annotation=True,  # This conflicts with annotations in JSON
            )
        self.assertIn("Cannot use both", str(context.exception))
        self.assertIn("use_annotation=True", str(context.exception))

    def test_create_from_template_json_annotations_without_use_annotation_succeeds(
        self,
    ):
        """Test that annotations work when use_annotation=False (default)"""
        # Given
        template_json: Dict[str, Any] = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Rate quality",
                    "options": [{"label_text": "Poor"}, {"label_text": "Excellent"}],
                }
            ],
            "annotations": [
                {
                    "type": "ANNOTATION",
                    "question": "Describe issues",
                    "related_model": "ALL",
                }
            ],
        }

        # Mock the template service methods for create_from_template_json flow
        mock_put_response = Mock()
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status = Mock()
        self.mock_api_client.put.return_value = mock_put_response

        # When - use_annotation defaults to False, so this should work
        evaluator = self.human_eval.create_from_template_json(
            json=template_json,
            name="Test Annotations Only",
            use_annotation=False,  # Explicit False
        )

        # Then
        self.assertIsNotNone(evaluator)

    def test_create_from_template_json_with_single_ref_type(self):
        """Test creating from template JSON with SINGLE_REF custom_type for CMOS-style evaluation"""
        # Given
        template_json: Dict[str, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "How similar is the target to the reference?",
                    "scale": 5,
                    "anchor_label": {
                        "label_text": {
                            "left": "Completely different",
                            "right": "Identical",
                        }
                    },
                }
            ],
        }

        # Mock the template service methods for create_from_template_json flow
        mock_put_response = Mock()
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status = Mock()
        self.mock_api_client.put.return_value = mock_put_response

        # When
        evaluator = self.human_eval.create_from_template_json(
            json=template_json,
            name="Test SINGLE_REF",
            custom_type="SINGLE_REF",
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CMOS)  # type: ignore
        self.assertIn(EvalType.CMOS, evaluator._supported_eval_types)  # type: ignore

    def test_create_from_template_json_with_custom_type_enum(self):
        """Test create_from_template_json using CustomType enum instead of string"""
        # Given
        template_json: Dict[str, Any] = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Which audio is better?",
                    "scale": 5,
                    "anchor_label": {
                        "label_text": {
                            "left": "File A is better",
                            "right": "File B is better",
                        }
                    },
                }
            ],
        }

        mock_put_response = Mock()
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status = Mock()
        self.mock_api_client.put.return_value = mock_put_response

        # When - using CustomType enum instead of string
        evaluator = self.human_eval.create_from_template_json(
            json=template_json,
            name="Test with CustomType enum",
            custom_type=CustomType.DOUBLE,
        )

        # Then
        self.assertIsNotNone(evaluator)
        self.assertEqual(evaluator._eval_config.eval_type, EvalType.CUSTOM_DOUBLE)  # type: ignore


if __name__ == "__main__":
    unittest.main()
