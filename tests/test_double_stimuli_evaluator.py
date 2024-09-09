import pytest
from unittest.mock import Mock

from typing import List, Optional

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.file import File
from podonos.errors.error import NotSupportedError
from podonos.evaluators.double_stimuli_evaluator import DoubleStimuliEvaluator
from tests.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV, TESTDATA_SPEECH_TWO_CH2_WAV

class MockDoubleStimuliEvaluator(DoubleStimuliEvaluator):
    def __init__(self, supported_evaluation_types: List[EvalType],
                 api_client=Mock(spec=APIClient), eval_config: Optional[EvalConfig] = None):
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


class TestDoubleStimuliEvaluator:
    def setup_method(self):
        self.api_client = Mock(spec=APIClient)
        self.eval_config = EvalConfig(type="SMOS")
        self.evaluator = MockDoubleStimuliEvaluator(
            supported_evaluation_types=[EvalType.SMOS], api_client=self.api_client, eval_config=self.eval_config
        )

    def test_add_files_without_init(self):
        self.evaluator._initialized = False
        target_audio_config = File(path="generated.wav", model_tag="model_target", tags=["target"],
                                   script="This is the target audio file")
        ref_audio_config = File(path="original.wav", model_tag="model_ref", tags=["reference"], script=None,
                                is_ref=True)

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_files(file0=target_audio_config, file1=ref_audio_config)

        assert "evaluator is not initialized" in str(excinfo.value)

    def test_add_file_not_supported(self):
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file(File(path="1.wav", model_tag="model1", tags=["test"]))
        assert "only supported" in str(excinfo.value)

    def test_add_files_unsupported_eval_type(self):
        self.evaluator._initialized = True

        target = File(path="target.wav", model_tag="model_target", tags=["generated"])
        ref = File(path="ref.wav", model_tag="model_ref", tags=["human"], is_ref=True)

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_files(file0=target, file1=ref)

        assert "Unsupported" in str(excinfo.value)

    def test_add_files_missing_ref(self):
        self.evaluator._initialized = True
        self.eval_config._eval_type = EvalType.CMOS

        file0 = File(path="file0.wav", model_tag="model0", tags=["file0"], script="We are the world")
        file1 = File(path="file1.wav", model_tag="model1", tags=["file1"])

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_files(file0=file0, file1=file1)

        assert "must be set" in str(excinfo.value)

    def test_generate_random_group_name(self):
        group_name = self.evaluator._generate_random_group_name()
        parts = group_name.split("_")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert len(parts[1]) == 36
