import logging
import time
import uuid
from typing import Union, List

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.audio import AudioConfig
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.errors.error import NotSupportedError

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class DoubleStimuliEvaluator(Evaluator):
    def __init__(self, supported_evaluation_type: List[EvalType], api_client: APIClient, eval_config: Union[EvalConfig, None] = None):
        super().__init__(api_client, eval_config)
        self._supported_evaluation_type = supported_evaluation_type
    
    def add_file(self, path: Union[str, None] = None, tags: Union[List[str], None] = None) -> None:
        raise NotSupportedError("This function is not supported in this Evaluation Type")
    
    def add_file_pair(self, target: AudioConfig, ref: AudioConfig) -> None:
        """Adds new files for speech evaluation.
        The files may be either in {wav, mp3} format. The files will be securely uploaded to
        Podonos service system.

        Args:
            target: The target audio file configuration. This is the audio file
                    that is being evaluated to determine if it is better or worse
                    than the reference file.
            ref:    The reference audio file configuration. This is the audio file
                    that serves as the standard or baseline for comparison with the
                    target audio file.

        Example:
        If you want to evaluate audio files together (e.g., similarity MOS):
            target_audio_config, ref_audio_config = AudioConfig(path="generated.wav", tags=['target']), AudioConfig(path="original.wav", tags=['reference'])
            add_file_pair(target=target_audio_config, ref=ref_audio_config)

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """
        
        if not self._initialized:
            raise ValueError("Try to add_file_pair once the evaluator is closed.")
        
        eval_config = self._get_eval_config()

        if eval_config.eval_type in self._supported_evaluation_type:
            group = self._generate_random_group_name()
            target_audio = self._set_audio(path=target.path, tags=target.tags, group=group, type=QuestionFileType.STIMULUS)
            ref_audio = self._set_audio(path=ref.path, tags=ref.tags, group=group, type=QuestionFileType.REF)
            self._eval_audios.append([target_audio, ref_audio])
    
    def _generate_random_group_name(self) -> str:
        current_time_milliseconds = int(time.time() * 1000)
        random_uuid = uuid.uuid4()
        return f"{current_time_milliseconds}_{random_uuid}"