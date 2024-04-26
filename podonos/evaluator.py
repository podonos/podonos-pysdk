import datetime
import logging
import os
from pathlib import Path
from typing import Dict
import requests
import time

from podonos.audio_meta import *
from podonos.constant import *
from podonos.default_config import DefaultConfig


# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class Evaluator:
    """Evaluator for a single type of evaluation session."""
    _initialized = None
    _api_key = None
    _api_base_url = None

    _eval_config = {}

    # Contains the metadata for all the audio files for evaluation.
    _eval_audio_json = []

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
        response = requests.post(f'{self._api_base_url}/clients/uploading-presigned-url',
                                 json=params, headers=headers)
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
            r = requests.put(presigned_url,
                             data=open(path, 'rb'),
                             headers=upload_headers)
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        # Timestamp in ISO 8601.
        upload_finish_at = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        return upload_start_at, upload_finish_at

    def __init__(self, api_key, api_base_url, eval_config):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._eval_config = eval_config
        self._initialized = True

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False

        self._api_key = None
        self._api_base_url = None
        self._eval_config = None

        self._eval_audio_json = []

    def add_file(self, **kwargs) -> None:
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

        path0 = None
        path1 = None

        # Check the input parameters.
        audio_json = {}
        if 'NMOS' == self._eval_config['eval_type']:
            if 'path' not in kwargs:
                raise ValueError(f'"path" must be set for the evaluation type {self._eval_config["eval_type"]}')
            path0 = kwargs['path']
            path_base0 = os.path.basename(path0)
            assert os.path.isfile(path0), f"File {path0} doesn't exist"
            assert os.access(path0, os.R_OK), f"File {path0} isn't readable"
            remote_object_name0 = os.path.join(self._eval_config['eval_creation_timestamp'], path_base0)
            log.debug(f'remote_object_name: {remote_object_name0}\n')
            nchannels0, framerate0, duration_in_ms0 = get_audio_info(path0)
            audio_json['name0'] = path_base0
            audio_json['nchannels0'] = nchannels0
            audio_json['framerate0'] = framerate0
            audio_json['duration_in_ms0'] = duration_in_ms0
            if 'tag' in kwargs:
                audio_json['tag'] = kwargs['tag']

        if 'SMOS' == self._eval_config['eval_type']:
            if 'path' in kwargs:
                raise ValueError(f'"path" must not be set for {self._eval_config["_eval_type"]}')
            if 'path0' not in kwargs or 'path1' not in kwargs:
                raise ValueError(f'Both "path0" and "path1" must be set for {self._eval_config["_eval_type"]}')
            path0 = kwargs['path0']
            path1 = kwargs['path1']
            path_base0 = os.path.basename(path0)
            path_base1 = os.path.basename(path1)
            assert os.path.isfile(path0), f"File {path0} doesn't exist"
            assert os.path.isfile(path1), f"File {path1} doesn't exist"
            assert os.access(path0, os.R_OK), f"File {path0} isn't readable"
            assert os.access(path1, os.R_OK), f"File {path1} isn't readable"
            remote_object_name0 = os.path.join(self._eval_config['eval_creation_timestamp'], path_base0)
            remote_object_name1 = os.path.join(self._eval_config['eval_creation_timestamp'], path_base1)
            log.debug(f'remote_object_names: {remote_object_name0} {remote_object_name1}')
            nchannels0, framerate0, duration_in_ms0 = get_audio_info(path0)
            nchannels1, framerate1, duration_in_ms1 = get_audio_info(path1)
            audio_json['name0'] = path_base0
            audio_json['name1'] = path_base1
            audio_json['nchannels0'] = nchannels0
            audio_json['nchannels1'] = nchannels1
            audio_json['framerate0'] = framerate0
            audio_json['framerate1'] = framerate1
            audio_json['duration_in_ms0'] = duration_in_ms0
            audio_json['duration_in_ms1'] = duration_in_ms1
            if 'tag0' in kwargs:
                audio_json['tag0'] = kwargs['tag0']
            if 'tag1' in kwargs:
                audio_json['tag1'] = kwargs['tag1']

        # Upload files
        # TODO: add lazy & background upload
        upload_start_at0, upload_finish_at0 = self._upload_one_file(remote_object_name0, path0)
        audio_json['uploadStartAt0'] = upload_start_at0
        audio_json['uploadFinishAt0'] = upload_finish_at0

        if path1 is not None:
            upload_start_at1, upload_finish_at1 = self._upload_one_file(remote_object_name1, path1)
            audio_json['uploadStartAt1'] = upload_start_at1
            audio_json['uploadFinishAt1'] = upload_finish_at1

        self._eval_audio_json.append(audio_json)

    def close(self) -> Dict[str, str]:
        """Closes the file uploading and evaluation session.
        This function holds until the file uploading finishes.

        Returns:
            JSON object containing the uploading status.

        Raises:
            ValueError: if this function is called before calling init().
        """

        # Create a json.
        session_json = self._eval_config
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_config['eval_creation_timestamp'], 'session.json')
        headers = {
            'x-api-key': self._api_key
        }
        params = {
            'filename': remote_object_name,
            'evaluation_id': self._api_key
        }
        response = requests.post(f'{self._api_base_url}/clients/uploading-presigned-url',
                                 json=params, headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError
        presigned_url = response.text
        # Strip the double quotation marks
        presigned_url = presigned_url.replace('"', '')

        upload_headers = {'Content-type': 'application/json'}
        try:
            r = requests.put(presigned_url,
                             json=session_json,
                             headers=upload_headers)
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        if r.status_code != 200:
            raise requests.exceptions.HTTPError

        # Call evaluation requested.
        params = {
            'eval_id': self._eval_config['eval_id'],
            'eval_type': self._eval_config['eval_type']
        }
        response = requests.post(f'{self._api_base_url}/request-evaluation',
                                 json=params, headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        result_obj = {'status': 'ok'}

        print(f'{bcolors.OK}Upload finished. You will receive en email once the evaluation is done.{bcolors.ENDC}')
        # Initialize variables.
        self._init_eval_variables()

        return result_obj
