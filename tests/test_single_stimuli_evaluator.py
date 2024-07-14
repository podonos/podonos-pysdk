import pytest
from unittest.mock import Mock

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.audio import AudioConfig
from podonos.core.config import EvalConfig
from podonos.errors.error import NotSupportedError
from podonos.evaluators.single_stimuli_evaluator import SingleStimuliEvaluator

class TestSingleStimuliEvaluator:
    def setup_method(self):
        self.api_client = Mock(spec=APIClient)
        self.eval_config = EvalConfig(type='NMOS')
        self.evaluator = SingleStimuliEvaluator(
            supported_evaluation_type=[EvalType.NMOS, EvalType.QMOS, EvalType.P808],
            api_client=self.api_client,
            eval_config=self.eval_config
        )

    def test_add_file_without_path(self):
        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file()
        assert '"path" must be set for the evaluation type NMOS' in str(excinfo.value)

    def test_add_file_before_initialized(self):
        self.evaluator._initialized = False
        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file(path='/a/b/0.wav')
        assert 'Try to add file once the evaluator is closed.' in str(excinfo.value)

    def test_add_file_pair_not_supported(self):
        target_audio_config = AudioConfig(path='target.wav', tags=['target'])
        ref_audio_config = AudioConfig(path='ref.wav', tags=['ref'])
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file_pair(target=target_audio_config, ref=ref_audio_config)
        assert 'This function is not supported in this Evaluation Type' in str(excinfo.value)
