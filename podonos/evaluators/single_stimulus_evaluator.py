import logging
from typing import Union, List

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from podonos.errors.error import NotSupportedError

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class SingleStimulusEvaluator(Evaluator):
    def __init__(self, supported_evaluation_type: List[EvalType], api_client: APIClient, eval_config: Union[EvalConfig, None] = None):
        super().__init__(api_client, eval_config)
        self._supported_evaluation_type = supported_evaluation_type
    
    def add_file(
        self, 
        file: File
    ) -> None:
        """Add new file for speech evaluation.
        The file may be either in {wav, mp3} format. The file will be securely uploaded to
        Podonos service system.

        Args:
            file: Object including path and tags

        Example:
        If you want to evaluate each audio file separately (e.g., Naturalness MOS):
            add_file(file=File(path='./test.wav', tags=['male', 'generated']))

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        eval_config = self._get_eval_config()
        if eval_config.eval_type in self._supported_evaluation_type:
            audio = self._set_audio(path=file.path, tags=file.tags, group=None, type=QuestionFileType.STIMULUS)
            self._eval_audios.append([audio])
    
    def add_file_pair(self, target: File, ref: File) -> None:
        raise NotSupportedError("This function is not supported in this Evaluation Type")
    
    def add_file_set(self, file1: File, file2: File) -> None:
        raise NotSupportedError("This function is not supported in this Evaluation Type")