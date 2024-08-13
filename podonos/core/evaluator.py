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
from podonos.core.upload_manager import UploadManager

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
    _evaluation: Evaluation = None

    # Upload manager. Lazy initialization when used for saving resources.
    _upload_manager: UploadManager = None
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
        self._evaluation = self._create_evaluation()

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

    def get_evaluation_id(self) -> str:
        """
        Returns the evaluation id for this evaluator

        Returns:
            Evaluation id in string
        """
        assert self._evaluation
        return self._evaluation.id

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
        
        if self._eval_config.eval_type not in self._supported_evaluation_type:
            raise ValueError("Not supported evaluation type")

        # Wait until file uploading finishes.
        assert self._upload_manager.wait_and_close()

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
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_config.eval_creation_timestamp, 'session.json')
        presigned_url = self._get_presigned_url_for_put_method(
            self.get_evaluation_id(), "session.json", remote_object_name, 0, QuestionFileType.META)
        try:
            response = self._api_client.put_json_presigned_url(url=presigned_url, data=session_json,
                                                               headers={'Content-type': 'application/json'})
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to upload session.json: {e}",
                            status_code=e.response.status_code if e.response else None)
        
        if self._eval_config.eval_auto_start:
            print(f'{TerminalColor.OK}Upload finished. The evaluation will start immediately.{TerminalColor.ENDC}')
        else:
            print(f'{TerminalColor.OK}Upload finished. Please start the evaluation at {PODONOS_WORKSPACE}.'
                  f'{TerminalColor.ENDC}')

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
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

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
    ) -> None:
        """
        Start uploading one file to server.

        Args:
            evaluation_id: New evaluation's id.
            remote_object_name: Path to the remote file name.
            path: Path to the local file.
            tags: List of tags on the file.
            type: Type used in QuestionFile.
            group: Group's name for combining with other files.
        Returns:
            None
        """
        # Get the presigned URL for one file
        presigned_url = self._get_presigned_url_for_put_method(evaluation_id, path, remote_object_name,
                                                               duration_in_ms, type, tags, group, script)
        # Lazy initialization of upload manager.
        if self._upload_manager is None:
            self._upload_manager = UploadManager(api_client=self._api_client, max_workers=MAX_UPLOAD_WORKER)
        self._upload_manager.add_file_to_queue(presigned_url, remote_object_name, path)
        return
    
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
    ) -> str:
        try:
            response = self._api_client.put(f"evaluations/{evaluation_id}/uploading-presigned-url", {
                "original_uri": path,
                "processed_uri": remote_object_name,
                "duration": duration_in_ms,
                "tags": tags,
                "type": type,
                "group": group,
                "script": script
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
    
    def _set_audio(self, path: str, tags: Optional[List[str]], script: Optional[str], group: Optional[str],
                   type: QuestionFileType) -> Audio:
        valid_path = self._validate_path(path)
        name, remote_object_name = self._get_name_and_remote_object_name(valid_path)
                
        log.debug(f'remote_object_name: {remote_object_name}\n')
        return Audio(
            path=valid_path, name=name, remote_object_name=remote_object_name, script=script,
            tags=tags, group=group, type=type
        )
    
    def _validate_path(self, path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")
            
        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")
        return path
    
    def _get_name_and_remote_object_name(self, valid_path: str) -> Tuple[str, str]:
        eval_config = self._get_eval_config()
        remote_object_name = os.path.join(eval_config.eval_creation_timestamp, generate_random_name())
        return valid_path, remote_object_name