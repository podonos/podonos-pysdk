import os
import json
import requests
from abc import ABC, abstractmethod
from typing import Tuple, Dict, List, Optional

from podonos.core.base import *
from podonos.common.constant import *
from podonos.common.enum import EvalType, Language, QuestionFileType
from podonos.common.exception import HTTPError
from podonos.common.util import generate_random_name
from podonos.core.api import APIClient
from podonos.core.audio import Audio
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.file import File
from podonos.core.query import Query, Question
from podonos.core.upload_manager import UploadManager


class Evaluator(ABC):
    """Evaluator for a single type of evaluation session."""

    _initialized: bool = False
    _api_client: APIClient
    _api_key: Optional[str] = None
    _eval_config: Optional[EvalConfig] = None
    _supported_evaluation_type: List[EvalType]
    _evaluation: Optional[Evaluation] = None

    # Upload manager. Lazy initialization when used for saving resources.
    _upload_manager: Optional[UploadManager] = None

    # Custom Query.
    _query: Optional[Query] = None

    # Contains the metadata for all the audio files for evaluation.
    _eval_audios: List[List[Audio]] = []
    _eval_audio_json = []

    def __init__(self, api_client: APIClient, eval_config: Optional[EvalConfig] = None):
        log.check(api_client, "api_client is not initialized.")
        self._api_client = api_client
        self._api_key = api_client.api_key
        self._eval_config = eval_config
        self._initialized = True
        self._eval_audios = []
        self._eval_audio_json = []
        self._evaluation = self._create_evaluation()

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False
        self._api_key = None
        self._eval_config = None
        self._eval_audios = []
        self._eval_audio_json = []

    @abstractmethod
    def add_file(self, file: File) -> None:
        pass

    @abstractmethod
    def add_files(self, file0: File, file1: File) -> None:
        pass

    def get_evaluation_id(self) -> str:
        """
        Returns the evaluation id for this evaluator

        Returns:
            Evaluation id in string
        """
        assert self._evaluation
        return self._evaluation.id

    def set_question(self, title: str, description: Optional[str] = None) -> None:
        log.check_notnone(title)
        if len(title) < 5:
            log.warning(f"Are you sure with such a short title {title}?")
        self._query = Query(question=Question(title, description))

    def close(self) -> Dict[str, str]:
        """Closes the file uploading and evaluation session.
        This function holds until the file uploading finishes.

        Returns:
            JSON object containing the uploading status.

        Raises:
            ValueError: if this function is called before calling init().
        """
        log.debug("Closing the evaluator")
        if not self._initialized or self._eval_config is None:
            raise ValueError("No evaluation session is open.")

        if self._eval_config.eval_type not in self._supported_evaluation_type:
            raise ValueError("Not supported evaluation type")

        if self._upload_manager is None:
            raise ValueError("Upload Manager is not defined")

        # Wait until file uploading finishes.
        log.debug("Wait until the upload manager shuts down all the upload workers")
        assert self._upload_manager.wait_and_close()

        log.info("Uploading the final pieces...")

        # Create a template if custom query exists
        self._create_template_with_question_and_evaluation()

        # Insert File data into database
        self._create_files_of_evaluation([audio for audio_list in self._eval_audios for audio in audio_list])

        # Get the upload time & finish time.
        upload_start, upload_finish = self._upload_manager.get_upload_time()
        for audio_list in self._eval_audios:
            audio_json_list = []
            for audio in audio_list:
                remote_object_name = audio.remote_object_name
                upload_start_at = upload_start[remote_object_name]
                upload_finish_at = upload_finish[remote_object_name]
                audio.set_upload_at(upload_start_at, upload_finish_at)
                audio_json_list.append(audio.to_dict())
            self._eval_audio_json.append(audio_json_list)

        # Create a json.
        session_json = self._eval_config.to_dict()
        session_json["query"] = self._query.to_dict() if self._query else None
        session_json["files"] = self._eval_audio_json

        presigned_url = self._get_presigned_url_for_put_method(
            self.get_evaluation_id(),
            "session.json",
        )

        try:
            response = self._api_client.put_json_presigned_url(
                url=presigned_url, data=session_json, headers={"Content-type": "application/json"})
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP error in uploading a json: {e}")
            raise HTTPError(
                f"Failed to upload session info json: {e}",
                status_code=e.response.status_code if e.response else None,
            )

        if self._eval_config.eval_auto_start:
            log.info(f"{TerminalColor.OK}Upload finished. The evaluation will start immediately.{TerminalColor.ENDC}")
        else:
            log.info(f"{TerminalColor.OK}Upload finished. Please start the evaluation at {PODONOS_WORKSPACE}." f"{TerminalColor.ENDC}")

        # Initialize variables.
        self._init_eval_variables()
        return {"status": "ok"}

    def _get_eval_config(self) -> EvalConfig:
        if not self._eval_config:
            raise ValueError("Evaluator is not initialized")
        return self._eval_config

    def _create_evaluation(self) -> Evaluation:
        """
        Create a new evaluation based on the evaluation configuration

        Raises:
            HTTPError: If the value is invalid

        Returns:
            Evaluation: Get new evaluation information
        """
        log.debug("Creates evaluation")
        eval_config = self._get_eval_config()
        try:
            response = self._api_client.post("evaluations", data=eval_config.to_create_request_dto())
            response.raise_for_status()
            evaluation = Evaluation.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def _upload_one_file(
        self,
        evaluation_id: str,
        remote_object_name: str,
        path: str,
    ) -> None:
        """
        Start uploading one file to server.

        Args:
            evaluation_id: New evaluation's id.
            remote_object_name: Path to the remote file name.
            path: Path to the local file.
        Returns:
            None
        """
        log.check_notnone(evaluation_id)
        log.check_notnone(remote_object_name)
        log.check_notnone(path)
        log.check_ne(evaluation_id, "")
        log.check_ne(remote_object_name, "")
        log.check_ne(path, "")

        # Get the presigned URL for one file
        log.debug(f"Adding to queue: {path}")
        if not self._eval_config:
            raise ValueError("No evaluation session is open.")

        # Lazy initialization of upload manager.
        if self._upload_manager is None:
            log.debug(f"max_upload_workers: {self._eval_config.max_upload_workers}")
            self._upload_manager = UploadManager(
                api_client=self._api_client,
                max_workers=self._eval_config.max_upload_workers,
            )

        if self._upload_manager:
            self._upload_manager.add_file_to_queue(evaluation_id, remote_object_name, path)
        return

    def _get_presigned_url_for_put_method(
        self,
        evaluation_id: str,
        remote_object_name: str,
    ) -> str:
        log.check_ne(evaluation_id, "")
        log.check_ne(remote_object_name, "")

        try:
            response = self._api_client.put(
                f"evaluations/{evaluation_id}/uploading-presigned-url",
                {
                    "processed_uri": remote_object_name,
                },
            )
            response.raise_for_status()
            return response.text.replace('"', "")
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP error in getting a presigned url: {e}")
            raise HTTPError(
                f"Failed to get presigned URL for {remote_object_name}: {e}",
                status_code=e.response.status_code if e.response else None,
            )

    def _create_files_of_evaluation(self, audios: List[Audio]):
        try:
            response = self._api_client.put(
                f"evaluations/{self.get_evaluation_id()}/files",
                {"files": [audio.to_create_file_dict() for audio in audios]},
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP error in adding file meta: {e}")
            raise HTTPError(
                f"Failed to create evaluation files: {e}",
                status_code=e.response.status_code if e.response else None,
            )

    def _create_template_with_question_and_evaluation(
        self,
    ) -> None:
        eval_config = self._get_eval_config()
        try:
            if not self._query:
                return None

            response = self._api_client.post(
                "templates",
                {
                    "evaluation_id": self.get_evaluation_id(),
                    "title": self._query.title,
                    "description": self._query.description,
                    "language": eval_config.eval_language.value,
                },
            )
            response.raise_for_status()
        except Exception as e:
            log.error(f"HTTP error in evaluation template generation: {e}")
            raise e

    def _set_audio(
        self,
        file: File,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
    ) -> Audio:
        log.check_ne(file.path, "")

        valid_path = self._validate_path(file.path)
        remote_object_name = self._get_remote_object_name()
        original_path, remote_path = self._process_original_path_and_remote_object_path_into_posix_style(valid_path, remote_object_name)

        log.debug(f"remote_object_name: {remote_object_name}")
        return Audio(
            path=valid_path,
            name=original_path,
            remote_object_name=remote_path,
            script=file.script,
            tags=file.tags,
            model_tag=file.model_tag,
            is_ref=file.is_ref,
            group=group,
            type=type,
            order_in_group=order_in_group,
        )

    @staticmethod
    def _validate_path(path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")

        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")
        return path

    def _get_remote_object_name(self) -> str:
        eval_config = self._get_eval_config()
        remote_object_name = os.path.join(eval_config.eval_creation_timestamp, generate_random_name())
        return remote_object_name

    @staticmethod
    def _process_original_path_and_remote_object_path_into_posix_style(original_path: str, remote_object_path: str) -> Tuple[str, str]:
        posix_original_path = original_path.replace("\\", "/")
        posix_remote_object_path = remote_object_path.replace("\\", "/")
        return posix_original_path, posix_remote_object_path
