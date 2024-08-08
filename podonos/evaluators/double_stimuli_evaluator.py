import logging
import time
import uuid
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

class DoubleStimuliEvaluator(Evaluator):
    def __init__(self, supported_evaluation_type: List[EvalType], api_client: APIClient, eval_config: Union[EvalConfig, None] = None):
        super().__init__(api_client, eval_config)
        self._supported_evaluation_type = supported_evaluation_type
    
    def add_file(self, file: File) -> None:
        raise NotSupportedError("The 'add_file' is only supported in these evaluation types: {'NMOS', 'QMOS', 'P808'}")
    
    def add_file_pair(self, target: File, ref: File) -> None:
        """Adds new files for speech evaluation of CMOS and DMOS
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
        If you want to evaluate audio files together (e.g., Comparative MOS):
            target_file, ref_file = File(path="generated.wav", tags=['target']), File(path="original.wav", tags=['reference'])
            add_file_pair(target=target_file, ref=ref_file)

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """
        
        if not self._initialized:
            raise ValueError("Try to add_file_pair once the evaluator is closed.")
        
        eval_config = self._get_eval_config()
        if eval_config.eval_type not in [EvalType.CMOS, EvalType.DMOS]:
            raise ValueError("The add_file_pair function is used for 'CMOS', 'DMOS'")
        
        if eval_config.eval_type in self._supported_evaluation_type:
            group = self._generate_random_group_name()
            target_audio = self._set_audio(path=target.path, tags=target.tags, script=target.script, group=group, type=QuestionFileType.STIMULUS)
            ref_audio = self._set_audio(path=ref.path, tags=ref.tags, script=ref.script, group=group, type=QuestionFileType.REF)
            self._eval_audios.append([target_audio, ref_audio])
    
    def add_file_set(self, file0: File, file1: File) -> None:
        """Adds a new set of files for evaluation.
        This function adds a set of files for evaluation purposes. The files may be either in {wav, mp3} format.
        The files will be securely uploaded to the Podonos service system.

        Args:
            file1: The first audio file configuration. This can be either a target or a reference file
                depending on the evaluation configuration.
            file2: The second audio file configuration. This can be either a target or a reference file
                depending on the evaluation configuration.

        Example:
        If you want to evaluate audio files together (e.g., Similarity MOS):
            file1, file2 = File(path="file1.wav", tags=['file1']), File(path="file2.wav", tags=['file2'])
            add_file_set(file1=file1, file2=file2)

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """
        
        if not self._initialized:
            raise ValueError("Try to add_file_set once the evaluator is closed.")
        
        eval_config = self._get_eval_config()
        if eval_config.eval_type not in [EvalType.SMOS, EvalType.PREF]:
            raise ValueError("The add_file_set function is used for 'SMOS', 'PREF'")
        
        if eval_config.eval_type in self._supported_evaluation_type:
            group = self._generate_random_group_name()
            audio1 = self._set_audio(path=file0.path, tags=file0.tags, script=file0.script, group=group, type=QuestionFileType.STIMULUS)
            audio2 = self._set_audio(path=file1.path, tags=file1.tags, script=file1.script, group=group, type=QuestionFileType.STIMULUS)
            self._eval_audios.append([audio1, audio2])

    def _generate_random_group_name(self) -> str:
        current_time_milliseconds = int(time.time() * 1000)
        random_uuid = uuid.uuid4()
        return f"{current_time_milliseconds}_{random_uuid}"