import datetime
import logging
import os
import requests
from typing import Tuple, Dict, List, Optional

from podonos.common.constant import *
from podonos.common.enum import EvalType, QuestionFileType
from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.audio import Audio
from podonos.core.config import EvalConfig
from podonos.core.evaluation import EvaluationInformation

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class Evaluator:
    """Evaluator for a single type of evaluation session."""
    _initialized: bool = False
    _api_client: APIClient
    _api_key: Optional[str] = None
    _eval_config: Optional[EvalConfig] = None

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

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False
        self._api_key = None
        self._eval_config = None
        self._eval_audios = []
        self._eval_audio_json = []

    def add_file(
        self, 
        path: Optional[str] = None,
        path0: Optional[str] = None,
        path1: Optional[str] = None,
        tag: Optional[str] = None,
        tag0: Optional[str] = None,
        tag1: Optional[str] = None
    ) -> None:
        """Adds new files for speech evaluation.
        The files may be either in {wav, mp3} format. The files will be securely uploaded to
        Podonos service system.

        Args:
        path: Path to the audio file to evaluate. Must be set for single file eval like NMOS.
        path0: Path to the audio file to evaluate. If this is set, path1 must be set. For pairwise files like SMOS.
        path1: Path to the audio file to evaluate. If this is set, path0 must be set. For pairwise files like SMOS.
        tag: A comma separated list of string tags for path. Optional.
        tag0: A comma separated list of string tags for path0. Optional.
        tag1: A comma separated list of string tags for path1. Optional.

        Example:
        If you want to evaluate each audio file separately (e.g., naturalness MOS):
            add_file(path='/a/b/0.wav')

        If you want to evaluate a pair of audio files (e.g., preferences or similarity MOS):
            add_file(path0='/a/b/0-0.wav', path1='/a/b/0-1.wav', tag0='ours', tag1='SOTA')

        If you want to evaluate a triple of audio files (e.g., comparative similarity MOS):
            add_file(path0='/a/b/0-ref.wav', path1='/a/b/0-0.wav', path2='/a/b/0-1.wav')

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        if self._eval_config is None:
            raise ValueError("Evaluation configuration is not set.")

        if self._eval_config.eval_type in [EvalType.NMOS, EvalType.QMOS, EvalType.SMOS, EvalType.P808]:
            if not path:
                raise ValueError(f'"path" must be set for the evaluation type {self._eval_config.eval_type}')
            
            audio = self._set_audio(path=path, tag=tag, group=None, eval_config=self._eval_config)
            self._eval_audios.append([audio])

        if EvalType.SMOS == self._eval_config.eval_type:
            if path is not None:
                raise ValueError(f'"path" must not be set for {self._eval_config.eval_type}')
            if not path0 or not path1:
                raise ValueError(f'Both "path0" and "path1" must be set for {self._eval_config.eval_type}')
            
            audio0 = self._set_audio(path0, tag0, None, self._eval_config)
            audio1 = self._set_audio(path1, tag1, None, self._eval_config)
            self._eval_audios.append([audio0, audio1])

    def upload_files(self, evaluation_id: str) -> None:
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
                    tags=[audio.tag] if audio.tag else [],
                    type=QuestionFileType.STIMULUS,
                    group=audio.group
                )
                audio.set_upload_at(upload_start_at, upload_finish_at)
                audio_json_list.append(audio.to_dict())
            
            self._eval_audio_json.append(audio_json_list)
    
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
        evaluation = self._create_evaluation()
        self.upload_files(evaluation_id=evaluation.id)

        # Create a json.
        session_json = self._eval_config.to_dict()
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_config.eval_creation_timestamp, 'session.json')
        presigned_url = self._get_presigned_url_for_put_method(evaluation.id, remote_object_name)
        try:
            response = self._api_client.put_json_presigned_url(url=presigned_url, data=session_json, headers={'Content-type': 'application/json'})
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to upload session.json: {e}", status_code=e.response.status_code if e.response else None)
        
        if self._eval_config.eval_auto_start:
            print(f'{bcolors.OK}Upload finished. The evaluation will start immediately.{bcolors.ENDC}')
        else:
            print(f'{bcolors.OK}Upload finished. Please start the evaluation at {PODONOS_WORKSPACE}.{bcolors.ENDC}')

        # Initialize variables.
        self._init_eval_variables()
        return {'status': 'ok'}

    def _create_evaluation(self) -> EvaluationInformation:
        """
        Create a new evaluation based on evaluation configuration

        Raises:
            HTTPError: If the value is invalid

        Returns:
            EvaluationInformation: Get new evaluation information
        """
        
        if not self._eval_config:
            raise ValueError("Evaluator is not initialized")
        try:
            response = self._api_client.post("evaluations", data=self._eval_config.to_create_request_dto())
            response.raise_for_status()
            evaluation = EvaluationInformation.from_dict(response.json())
            self._eval_config.eval_id = evaluation.id
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def _upload_one_file(
        self, 
        evaluation_id: str, 
        remote_object_name: str, 
        path: str,
        tags: List[str] = [],
        type: QuestionFileType = QuestionFileType.STIMULUS,
        group: Optional[str] = None,
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
        presigned_url = self._get_presigned_url_for_put_method(evaluation_id, remote_object_name, tags, type, group)

        # Timestamp in ISO 8601.
        upload_start_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        self._api_client.put_file_presigned_url(presigned_url, path)
        upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        return upload_start_at, upload_finish_at
    
    def _get_presigned_url_for_put_method(
        self, 
        evaluation_id: str, 
        remote_object_name: str,
        tags: List[str] = [],
        type: QuestionFileType = QuestionFileType.STIMULUS,
        group: Optional[str] = None,
    ) -> str:
        try:
            response = self._api_client.put(f"evaluations/{evaluation_id}/uploading-presigned-url", {
                "filename": remote_object_name,
                "tags": tags,
                "type": type,
                "group": group
            })
            response.raise_for_status()
            return response.text.replace('"', '')
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to get presigned URL for {remote_object_name}: {e}", status_code=e.response.status_code if e.response else None)
    
    def _post_request_evaluation(self) -> None:
        if self._eval_config is None:
            raise ValueError("No evaluation session is open.")
        
        try:
            response = self._api_client.post("request-evaluation", {
                'eval_id': self._eval_config.eval_id,
                'eval_type': self._eval_config.eval_type.value
            })
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
            raise HTTPError(f"Failed to request evaluation: {e}", status_code=e.response.status_code if e.response else None)
    
    def _set_audio(self, path: str, tag: Optional[str], group: Optional[str], eval_config: EvalConfig) -> Audio:
        valid_path = self._validate_path(path)
        name, remote_name = self._get_name_and_remote_name(valid_path, eval_config)
                
        log.debug(f'remote_object_name: {remote_name}\n')
        return Audio(
            path=valid_path, name=name, remote_name=remote_name,
            tag=tag, group=group
        )
    
    def _validate_path(self, path: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")
            
        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")
        return path
    
    def _get_name_and_remote_name(self, valid_path: str, eval_config: EvalConfig) -> Tuple[str, str]:
        name = os.path.basename(valid_path)
        remote_name = os.path.join(eval_config.eval_creation_timestamp, name)
        return name, remote_name