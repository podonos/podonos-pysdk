import datetime
import logging
import os
import requests
from typing import Tuple, Dict, List, Optional

from podonos.common.constant import *
from podonos.common.enum import EvalType
from podonos.core.audio import Audio
from podonos.core.config import EvalConfig

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class Evaluator:
    """Evaluator for a single type of evaluation session."""
    _initialized: bool = False
    _api_key: Optional[str] = None
    _api_url: Optional[str] = None
    _eval_config: Optional[EvalConfig] = None

    # Contains the metadata for all the audio files for evaluation.
    _eval_audios: List[List[Audio]] = []
    _eval_audio_json = []

    def __init__(
        self, 
        api_key: str, 
        api_url: str, 
        eval_config: Optional[EvalConfig] = None
    ):
        self._api_key = api_key
        self._api_url = api_url
        self._eval_config = eval_config
        self._initialized = True

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False
        self._api_key = None
        self._api_url = None
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

        if self._eval_config.eval_type in [EvalType.NMOS, EvalType.P808]:
            if not path:
                raise ValueError(f'"path" must be set for the evaluation type {self._eval_config.eval_type}')
            
            audio = self._set_audio(path, tag, self._eval_config)
            self._eval_audios.append([audio])

        if EvalType.SMOS == self._eval_config.eval_type:
            if path is not None:
                raise ValueError(f'"path" must not be set for {self._eval_config.eval_type}')
            if not path0 or not path1:
                raise ValueError(f'Both "path0" and "path1" must be set for {self._eval_config.eval_type}')
            
            audio0 = self._set_audio(path0, tag0, self._eval_config)
            audio1 = self._set_audio(path1, tag1, self._eval_config)
            self._eval_audios.append([audio0, audio1])

        # Upload files
        # TODO: add lazy & background upload
        self.upload_files()

    def upload_files(self) -> None:
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
                upload_start_at, upload_finish_at = self._upload_one_file(audio.remote_name, audio.path)
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
        

        # Create a json.
        session_json = self._eval_config.to_dict()
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_config.eval_creation_timestamp, 'session.json')
        headers = {
            'x-api-key': self._api_key
        }
        params = {
            'filename': remote_object_name,
            'evaluation_id': self._api_key
        }
        response = requests.post(
            f'{self._api_url}/customers/uploading-presigned-url',
            json=params, headers=headers
        )
        
        if response.status_code != 200:
            raise requests.exceptions.HTTPError
        presigned_url = response.text
        
        # Strip the double quotation marks
        presigned_url = presigned_url.replace('"', '')

        upload_headers = {'Content-type': 'application/json'}
        try:
            r = requests.put(
                presigned_url,
                json=session_json,
                headers=upload_headers
            )
            if r.status_code != 200:
                raise requests.exceptions.HTTPError
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        
        # Call evaluation requested.
        response = requests.post(
            f'{self._api_url}/request-evaluation',
            json={
                'eval_id': self._eval_config.eval_id,
                'eval_type': self._eval_config.eval_type.value
            }, 
            headers=headers
        )
        
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        result_obj = {'status': 'ok'}

        print(f'{bcolors.OK}Upload finished. You will receive en email once the evaluation is done.{bcolors.ENDC}')
        
        # Initialize variables.
        self._init_eval_variables()

        return result_obj
    
    def _upload_one_file(self, remote_object_name: str, path: str) -> Tuple[str, str]:
        """
        Upload one file to server.

        Args:
            remote_object_name: Path to the remote file name.
            path: Path to the local file.

        Returns:
            upload_start_at: Upload start time in ISO 8601 string.
            upload_finish_at: Upload start time in ISO 8601 string.
        """
        # Get the presigned URL for files
        headers = {
            'x-api-key': self._api_key
        }
        params = {
            'filename': remote_object_name,
            'evaluation_id': self._api_key
        }
        response = requests.post(
            f'{self._api_url}/customers/uploading-presigned-url',
            json=params, headers=headers
        )
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        presigned_url = response.text
        # Strip the double quotation marks
        presigned_url = presigned_url.replace('"', '')

        # Upload the file.
        _, ext = os.path.splitext(path)
        if ext == '.wav':
            upload_headers = {'Content-type': 'audio/wav'}
        elif ext == '.mp3':
            upload_headers = {'Content-type': 'audio/mpeg'}
        elif ext == '.json':
            upload_headers = {'Content-type': 'application/json'}
        else:
            upload_headers = {'Content-type': 'application/octet-stream'}

        # Timestamp in ISO 8601.
        upload_start_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        try:
            r = requests.put(
                presigned_url,
                data=open(path, 'rb'),
                headers=upload_headers
            )
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        # Timestamp in ISO 8601.
        upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        return upload_start_at, upload_finish_at
    
    def _set_audio(self, path: str, tag: Optional[str], eval_config: EvalConfig) -> Audio:
        valid_path = self._validate_path(path)
        name, remote_name = self._get_name_and_remote_name(valid_path, eval_config)
                
        log.debug(f'remote_object_name: {remote_name}\n')
        return Audio(
            path=valid_path, name=name, remote_name=remote_name, tag=tag
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