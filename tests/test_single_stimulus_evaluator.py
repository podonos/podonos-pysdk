import pytest
from unittest.mock import Mock

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.file import File
from podonos.errors.error import NotSupportedError
from podonos.evaluators.single_stimulus_evaluator import SingleStimulusEvaluator

class TestSingleStimulusEvaluator:
    def setup_method(self):
        self.api_client = Mock(spec=APIClient)
        self.eval_config = EvalConfig(type='NMOS')
        self.evaluator = SingleStimulusEvaluator(
            supported_evaluation_type=[EvalType.NMOS, EvalType.QMOS, EvalType.P808],
            api_client=self.api_client,
            eval_config=self.eval_config
        )

    def test_add_file_before_initialized(self):
        self.evaluator._initialized = False
        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file(file=File(path='./male.wav', tags=['male']))
        assert 'Try to add file once the evaluator is closed.' in str(excinfo.value)

    def test_add_file_pair_not_supported(self):
        target_audio_config = File(path='target.wav', tags=['target'])
        ref_audio_config = File(path='ref.wav', tags=['ref'])
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file_pair(target=target_audio_config, ref=ref_audio_config)
        assert "Not supported function. Use one of {'CMOS', 'DMOS'}" in str(excinfo.value)

    def test_add_file_set_not_supported(self):
        file0 = File(path='original.wav', tags=['original'])
        file1 = File(path='generated.wav', tags=['generated'])
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file_set(file0=file0, file1=file1)
        assert "Not supported function. Use one of {'SMOS', 'PREF'}" in str(excinfo.value)
