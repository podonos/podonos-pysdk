from typing import Union, List

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.base import *
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from podonos.errors.error import NotSupportedError


class SingleStimulusEvaluator(Evaluator):
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
        """Add new file for speech evaluation.
        The file may be either in {wav, mp3} format. The file will be securely uploaded to
        Podonos service system.

        Args:
            file: File object including the path, the model tag, the other tags, and the script.

        Example:
        If you want to evaluate each audio file separately (e.g., Naturalness MOS):
            add_file(file=File(path='./test.wav', model_tag='my_new_model1', tags=['male', 'generated'],
                               script='hello there'))

        Returns: None

        Raises:
            ValueError: if this function is called before calling init()
            FileNotFoundError: if a given file is not found.
        """
        log.check(file, "file is not set")

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        eval_config = self._get_eval_config()
        if eval_config.eval_type in self._supported_evaluation_types:
            if eval_config.eval_use_annotation and file.script is None:
                raise ValueError(
                    "Annotation evaluation is enabled (eval_use_annotation=True), "
                    "but no script is provided in File. Please provide a corresponding script."
                )

            audio = self._set_audio(
                file=file,
                group=None,
                type=QuestionFileType.STIMULUS,
                order_in_group=0,
            )
            self._eval_audios.append([audio])
            self._upload_one_file(
                evaluation_id=self.get_evaluation_id(),
                remote_object_name=audio.remote_object_name,
                path=audio.path,
            )

    def add_files(self, target: File, ref: File) -> None:
        raise NotSupportedError("The 'add_files' is only supported for group evaluations like "
                                "{'CMOS', 'DMOS', 'PREF'}")
