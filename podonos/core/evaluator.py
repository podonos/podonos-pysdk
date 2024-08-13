import datetime
import logging
import os
import requests
from abc import ABC, abstractmethod
from typing import Tuple, Dict, List, Optional

from podonos.common.constant import *
from podonos.common.enum import EvalType, QuestionFileType
from podonos.common.exception import HTTPError
from podonos.common.util import generate_random_name
from podonos.core.api import APIClient
from podonos.core.audio import Audio
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.file import File

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class Evaluator(ABC):
    """Evaluator for a single type of evaluation session."""
    _initialized: bool = False
    _api_client: APIClient
    _api_key: Optional[str] = None
    _eval_config: Optional[EvalConfig] = None
    _supported_evaluation_type: List[EvalType]

    # Contains the metadata for all the audio files for evaluation.
    _eval_audios: List[List[Audio]] = []
    _eval_audio_json = []

    def __init__(
        self, 
        api_client: APIClient,
        eval_config: Optional[EvalConfig] = None
    ):
        self._api_client = api_client
        self._api_key = api_client.api_key
        self._eval_config = eval_config
        self._initialized = True
        self._eval_audios = []
        self._eval_audio_json = []

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False
        self._api_key = None
        self._eval_config = None
        self._eval_audios = []
        self._eval_audio_json = []
    
    @abstractmethod
    def add_file(
        self, 
        file: File
    ) -> None:
        pass
    
    @abstractmethod
    def add_file_pair(
        self, 
        target: File,
        ref: File
    ) -> None:
        pass
    
    @abstractmethod
    def add_file_set(
        self, 
        file0: File,
        file1: File
    ) -> None:
        pass
    
    def close(self) -> Dict[str, str]:
        """Closes the file uploading and evaluation session.
        This function holds until the file uploading finishes.

        Returns:
            JSON object containing the uploading status.

        Raises:
            ValueError: if this function is called before calling init().
        """
        if not self._initialized or self._eval_config is None:
            raise ValueError("No evaluation session is open.")
        
        # Upload files
        # TODO: add lazy & background upload
        if self._eval_config.eval_type not in self._supported_evaluation_type:
            raise ValueError("Not supported evaluation type")
        
        evaluation = self._create_evaluation()
        self._upload_files(evaluation_id=evaluation.id)

        # Create a json.
        session_json = self._eval_config.to_dict()
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_config.eval_creation_timestamp, 'session.json')
        presigned_url = self._get_presigned_url_for_put_method(evaluation.id, "session.json", remote_object_name, 0, QuestionFileType.META)
        try:
            response = self._api_client.put_json_presigned_url(url=presigned_url, data=session_json, headers={'Content-type': 'application/json'})
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to upload session.json: {e}", status_code=e.response.status_code if e.response else None)
        
        if self._eval_config.eval_auto_start:
            print(f'{TerminalColor.OK}Upload finished. The evaluation will start immediately.{TerminalColor.ENDC}')
        else:
            print(f'{TerminalColor.OK}Upload finished. Please start the evaluation at {PODONOS_WORKSPACE}.{TerminalColor.ENDC}')

        # Initialize variables.
        self._init_eval_variables()
        return {'status': 'ok'}

    def _get_eval_config(self) -> EvalConfig:
        if not self._eval_config:
            raise ValueError("Evaluator is not initialized")
        return self._eval_config

    def _create_evaluation(self) -> Evaluation:
        """
        Create a new evaluation based on evaluation configuration

        Raises:
            HTTPError: If the value is invalid

        Returns:
            Evaluation: Get new evaluation information
        """
        
        eval_config = self._get_eval_config()
        try:
            response = self._api_client.post("evaluations", data=eval_config.to_create_request_dto())
            response.raise_for_status()
            evaluation = Evaluation.from_dict(response.json())
            eval_config.eval_id = evaluation.id
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")
    
    def _upload_files(self, evaluation_id: str) -> None:
        """Uploads the files for evaluation.
        This function holds until the file uploading finishes.

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
        """
        if not self._initialized or self._eval_config is None:
            raise ValueError("No evaluation session is open.")
        
        for audio_list in self._eval_audios:
            audio_json_list = []
            for audio in audio_list:
                # Get the presigned URL for filename
                upload_start_at, upload_finish_at = self._upload_one_file(
                    evaluation_id=evaluation_id, 
                    remote_object_name=audio.remote_name, 
                    path=audio.path,
                    duration_in_ms=audio.metadata.duration_in_ms,
                    tags=audio.tags if audio.tags else [],
                    type=audio.type,
                    group=audio.group,
                    script=audio.script,
                    order_in_group=audio.order_in_group,
                )
                audio.set_upload_at(upload_start_at, upload_finish_at)
                audio_json_list.append(audio.to_dict())
            
            self._eval_audio_json.append(audio_json_list)

    def _upload_one_file(
        self, 
        evaluation_id: str, 
        remote_object_name: str, 
        path: str,
        duration_in_ms: int,
        type: QuestionFileType,
        tags: List[str] = [],
        group: Optional[str] = None,
        script: Optional[str] = None,
        order_in_group: int = 0,
    ) -> Tuple[str, str]:
        """
        Upload one file to server.

        Args:
            evaluation_id: New evaluation's id.
            remote_object_name: Path to the remote file name.
            path: Path to the local file.
            tags: Specific name list about file.
            type: Type used in QuestionFile.
            group: Group's name for combining with other files.
        Returns:
            upload_start_at: Upload start time in ISO 8601 string.
            upload_finish_at: Upload start time in ISO 8601 string.
        """
        # Get the presigned URL for files
        presigned_url = self._get_presigned_url_for_put_method(evaluation_id, path, remote_object_name, duration_in_ms, type, tags, group, script, order_in_group)

        # Timestamp in ISO 8601.
        upload_start_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        self._api_client.put_file_presigned_url(presigned_url, path)
        upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        return upload_start_at, upload_finish_at
    
    def _get_presigned_url_for_put_method(
        self, 
        evaluation_id: str, 
        path: str,
        remote_object_name: str,
        duration_in_ms: int,
        type: QuestionFileType,
        tags: List[str] = [],
        group: Optional[str] = None,
        script: Optional[str] = None,
        order_in_group: int = 0
    ) -> str:
        try:
            response = self._api_client.put(f"evaluations/{evaluation_id}/uploading-presigned-url", {
                "original_uri": path,
                "processed_uri": remote_object_name,
                "duration": duration_in_ms,
                "tags": tags,
                "type": type,
                "group": group,
                "script": script,
                "order_in_group": order_in_group
            })
            response.raise_for_status()
            return response.text.replace('"', '')
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to get presigned URL for {remote_object_name}: {e}", status_code=e.response.status_code if e.response else None)
    
    def _post_request_evaluation(self) -> None:        
        eval_config = self._get_eval_config()
        try:
            response = self._api_client.post("request-evaluation", {
                'eval_id': eval_config.eval_id,
                'eval_type': eval_config.eval_type.get_type()
            })
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to request evaluation: {e}", status_code=e.response.status_code if e.response else None)
    
    def _set_audio(self, path: str, tags: Optional[List[str]], script: Optional[str], group: Optional[str], type: QuestionFileType, order_in_group: int) -> Audio:
        valid_path = self._validate_path(path)
        name, remote_name = self._get_name_and_remote_name(valid_path)
                
        log.debug(f'remote_object_name: {remote_name}\n')
        return Audio(
            path=valid_path, name=name, remote_name=remote_name, script=script,
            tags=tags, group=group, type=type, order_in_group=order_in_group
        )
    
    def _validate_path(self, path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")
            
        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")
        return path
    
    def _get_name_and_remote_name(self, valid_path: str) -> Tuple[str, str]:
        eval_config = self._get_eval_config()
        remote_name = os.path.join(eval_config.eval_creation_timestamp, generate_random_name())
        return valid_path, remote_name