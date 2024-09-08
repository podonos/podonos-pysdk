import time
import uuid
from typing import Union, List

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.base import *
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from podonos.errors.error import NotSupportedError


class DoubleStimuliEvaluator(Evaluator):
    def __init__(
        self,
        supported_evaluation_types: List[EvalType],
        api_client: APIClient,
        eval_config: Union[EvalConfig, None] = None,
    ):
        log.check(api_client, "api_client is not initialized")
        super().__init__(api_client, eval_config)
        self._supported_evaluation_types = supported_evaluation_types

    def add_file(self, file: File) -> None:
        raise NotSupportedError("The 'add_file' is only supported in single file evaluation types: "
                                "{'NMOS', 'QMOS', 'P808'}")

    def add_files(self, file0: File, file1: File) -> None:
        """Adds files for speech evaluation in an ordered or unordered way. If the evaluation requires an order of
        the input files, the order is kept strictly. The files will be securely uploaded to Podonos service system.

        Args:
            file0: The first audio file configuration.
            file1: The second audio file configuration.

        Example:
        If you want to evaluate audio files together (e.g., Comparative MOS):
            f0 = File(path="/path/to/generated.wav", model_tag='my_new_model1', tags=['male', 'english'], is_ref=True)
            f1 = File(path="/path/to/original.wav", model_tag='my_new_model2', tags=['male', 'english', 'param1'])
            add_files(file0=f0, file1=f1)

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """
        log.check(file0, "file0 is not set")
        log.check(file1, "file1 is not set")

        if not self._initialized:
            raise ValueError("Try to add_files once the evaluator is not initialized.")

        eval_config = self._get_eval_config()
        if eval_config.eval_type in self._supported_evaluation_types:
            raise ValueError(f"Unsupported evaluation type: {eval_config.eval_type}")
        if eval_config.eval_type not in [EvalType.SMOS, EvalType.PREF, EvalType.CMOS, EvalType.DMOS]:
            raise ValueError("The add_files is used for such evaluations that require multiple files.")

        group = self._generate_random_group_name()
        print(eval_config.eval_type.value)
        if eval_config.eval_type == EvalType.PREF:
            # Files are ordered stimulus.
            audio0 = self._set_audio(file=file0, group=group, type=QuestionFileType.STIMULUS, order_in_group=0)
            audio1 = self._set_audio(file=file1, group=group, type=QuestionFileType.STIMULUS, order_in_group=1)
        elif eval_config.eval_type == EvalType.SMOS:
            # Files are unordered stimulus.
            audio0 = self._set_audio(file=file0, group=group, type=QuestionFileType.STIMULUS, order_in_group=0)
            audio1 = self._set_audio(file=file1, group=group, type=QuestionFileType.STIMULUS, order_in_group=1)
        else:  # CMOS, DMOS
            # Files are ordered stimulus, one of them must be a reference.
            if file0.is_ref == file1.is_ref:
                raise ValueError("One of the input files must be set as a reference.")
            audio0_type = QuestionFileType.REF if file0.is_ref else QuestionFileType.STIMULUS
            audio1_type = QuestionFileType.REF if file1.is_ref else QuestionFileType.STIMULUS
            audio0 = self._set_audio(file=file0, group=group, type=audio0_type, order_in_group=0)
            audio1 = self._set_audio(file=file1, group=group, type=audio1_type, order_in_group=1)
        self._eval_audios.append([audio0, audio1])

        self._upload_one_file(
            evaluation_id=self.get_evaluation_id(), remote_object_name=audio0.remote_object_name, path=audio0.path)
        self._upload_one_file(
            evaluation_id=self.get_evaluation_id(), remote_object_name=audio1.remote_object_name, path=audio1.path)

    @staticmethod
    def _generate_random_group_name() -> str:
        current_time_milliseconds = int(time.time() * 1000)
        random_uuid = uuid.uuid4()
        name = f"{current_time_milliseconds}_{random_uuid}"
        log.check_gt(len(name), 5)
        log.check_lt(len(name), 100)
        return name
