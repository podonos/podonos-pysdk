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


class MockDoubleStimuliEvaluator(DoubleStimuliEvaluator):
    def __init__(self, supported_evaluation_type: List[EvalType], api_client=Mock(spec=APIClient), eval_config: Optional[EvalConfig] = None):
        super().__init__(supported_evaluation_type, api_client, eval_config)

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
            supported_evaluation_type=[EvalType.SMOS], api_client=self.api_client, eval_config=self.eval_config
        )

    def test_add_file_pair_without_init(self):
        self.evaluator._initialized = False
        target_audio_config = File(path="generated.wav", tags=["target"], script="This is target audio file")
        ref_audio_config = File(path="original.wav", tags=["reference"], script=None)

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file_pair(target=target_audio_config, ref=ref_audio_config)

        assert "Try to add_file_pair once the evaluator is closed." in str(excinfo.value)

    def test_add_file_not_supported(self):
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file(File(path="1.wav", tags=["test"]))
        assert "The 'add_file' is only supported in these evaluation types: {'NMOS', 'QMOS', 'P808'}" in str(excinfo.value)

    def test_add_file_pair_unsupported_eval_type(self):
        self.evaluator._initialized = True

        target = File(path="target.wav", tags=["generated"])
        ref = File(path="ref.wav", tags=["human"])

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file_pair(target=target, ref=ref)

        assert "The add_file_pair function is used for 'CMOS', 'DMOS'" in str(excinfo.value)

    def test_add_file_set_unsupported_eval_type(self):
        self.evaluator._initialized = True
        self.eval_config._eval_type = EvalType.CMOS

        file0 = File(path="file1.wav", tags=["file1"], script="We are the world")
        file1 = File(path="file2.wav", tags=["file2"])

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file_set(file0=file0, file1=file1)

        assert "The add_file_set function is used for 'SMOS', 'PREF'" in str(excinfo.value)

    def test_close_upsupported_eval_type(self):
        self.evaluator._initialized = True
        self.eval_config._eval_type = EvalType.PREF

        file0 = File(path="file1.wav", tags=["file1"])
        file1 = File(path="file2.wav", tags=["file2"])
        self.evaluator.add_file_set(file0=file0, file1=file1)

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.close()

        assert "Not supported evaluation type" in str(excinfo.value)

    def test_generate_random_group_name(self):
        group_name = self.evaluator._generate_random_group_name()
        parts = group_name.split("_")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert len(parts[1]) == 36
