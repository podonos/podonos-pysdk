import logging
from typing import Optional, Union, List

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.audio import AudioConfig
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.errors.error import NotSupportedError

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class SingleStimuliEvaluator(Evaluator):
    def __init__(self, supported_evaluation_type: List[EvalType], api_client: APIClient, eval_config: Union[EvalConfig, None] = None):
        super().__init__(api_client, eval_config)
        self._supported_evaluation_type = supported_evaluation_type
    
    def add_file(
        self, 
        path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Adds new files for speech evaluation.
        The files may be either in {wav, mp3} format. The files will be securely uploaded to
        Podonos service system.

        Args:
        path: Path to the audio file to evaluate. Must be set for single file eval like NMOS.
        tag: A comma separated list of string tags for path. Optional.

        Example:
        If you want to evaluate each audio file separately (e.g., naturalness MOS):
            add_file(path='/a/b/0.wav')

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        eval_config = self._get_eval_config()

        if eval_config.eval_type in self._supported_evaluation_type:
            if not path:
                raise ValueError(f'"path" must be set for the evaluation type {eval_config.eval_type.value}')
            
            audio = self._set_audio(path=path, tags=tags, group=None, type=QuestionFileType.STIMULUS)
            self._eval_audios.append([audio])
    
    def add_file_pair(self, target: AudioConfig, ref: AudioConfig) -> None:
        raise NotSupportedError("This function is not supported in this Evaluation Type")