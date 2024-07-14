import pytest
from unittest.mock import Mock

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.audio import AudioConfig
from podonos.core.config import EvalConfig
from podonos.errors.error import NotSupportedError
from podonos.evaluators.double_stimuli_evaluator import DoubleStimuliEvaluator

# Pytest 테스트 클래스
class TestDoubleStimuliEvaluator:
    def setup_method(self):
        self.api_client = Mock(spec=APIClient)
        self.eval_config = EvalConfig(type='SMOS')
        self.evaluator = DoubleStimuliEvaluator(
            supported_evaluation_type=[EvalType.SMOS],
            api_client=self.api_client,
            eval_config=self.eval_config
        )

    def test_add_file_pair_without_init(self):
        self.evaluator._initialized = False
        target_audio_config = AudioConfig(path='generated.wav', tags=['target'])
        ref_audio_config = AudioConfig(path='original.wav', tags=['reference'])

        with pytest.raises(ValueError) as excinfo:
            self.evaluator.add_file_pair(target=target_audio_config, ref=ref_audio_config)
        
        assert 'Try to add_file_pair once the evaluator is closed.' in str(excinfo.value)
    
    def test_add_file_not_supported(self):
        with pytest.raises(NotSupportedError) as excinfo:
            self.evaluator.add_file(path="1.wav", tags=["test"])
        assert 'This function is not supported in this Evaluation Type' in str(excinfo.value)

    def test_generate_random_group_name(self):
        group_name = self.evaluator._generate_random_group_name()
        parts = group_name.split('_')
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert len(parts[1]) == 36 
