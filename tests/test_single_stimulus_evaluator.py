import pytest
from unittest.mock import Mock

from typing import List, Optional

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.file import File
from podonos.errors.error import NotSupportedError
from podonos.evaluators.single_stimulus_evaluator import SingleStimulusEvaluator


class MockDoubleStimuliEvaluator(SingleStimulusEvaluator):
    def __init__(self, supported_evaluation_types: List[EvalType], api_client=Mock(spec=APIClient), eval_config: Optional[EvalConfig] = None):
        super().__init__(supported_evaluation_types, api_client, eval_config)

    def _create_evaluation(self) -> Evaluation:
        evaluation_config = {
            "id": "mock_id",
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-05-21T06:18:09.659270Z",
            "updated_time": "2024-05-22T06:18:09.659270Z",
        }
        evaluation = Evaluation.from_dict(evaluation_config)
        return evaluation


class TestSingleStimulusEvaluator:
    def setup_method(self):
        self.api_client = Mock(spec=APIClient)
        self.eval_config = EvalConfig(type="NMOS")
        self.evaluator = MockDoubleStimuliEvaluator(
            supported_evaluation_types=[EvalType.NMOS, EvalType.QMOS, EvalType.P808], api_client=self.api_client, eval_config=self.eval_config
        )

    def test_add_file_before_initialized(self):
        self.evaluator._initialized = False
        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file(file=File(path="./male.wav", model_tag="model1", tags=["male"]))
        assert "Try to add file once the evaluator is closed." in str(excinfo.value)

    def test_add_files_not_supported(self):
        target_audio_config = File(path="target.wav", model_tag="model2", tags=["target"])
        ref_audio_config = File(path="ref.wav", model_tag="model1", tags=["ref"])
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_files(file0=target_audio_config, file1=ref_audio_config)
        assert "only supported" in str(excinfo.value)
