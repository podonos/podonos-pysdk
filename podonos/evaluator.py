import datetime
import logging
import os
from pathlib import Path
from typing import Dict
import requests
import time

from podonos.audio_meta import *
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
    # _eval_id = None
    # _eval_name = None
    # _eval_desc = None
    # _eval_type = None
    # _eval_language = None
    # _num_eval = DefaultConfig.NUM_EVAL
    # _eval_expected_due = None
    # _eval_expected_due_tzname = None
    # _eval_creation_timestamp = None

    # Contains the metadata for all the audio files for evaluation.
    _eval_audio_json = []

    def __init__(self, api_key, api_base_url, eval_config):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._eval_config = eval_config
        # self._eval_id = eval_id
        # self._eval_name = eval_name
        # self._eval_desc = eval_desc
        # self._eval_type = eval_type
        # self._eval_language = eval_language
        # self._num_eval = num_eval
        # self._eval_expected_due = expected_due
        # self._eval_expected_due_tzname = expected_due_tzname
        # self._eval_creation_timestamp = creation_timestamp
        self._initialized = True

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False

        self._api_key = None
        self._api_base_url = None
        self._eval_config = None
        # self._eval_id = None
        # self._eval_name = None
        # self._eval_desc = None
        # self._eval_type = DefaultConfig.TYPE
        # self._eval_language = DefaultConfig.LAN
        # self._num_eval = DefaultConfig.NUM_EVAL
        # self._eval_expected_due = None
        # self._eval_expected_due_tzname = None
        # self._eval_creation_timestamp = None

        self._eval_audio_json = []

    def add_file(self, **kwargs) -> None:
        """Adds new files for speech evaluation.
        The files may be either in {wav, mp3} format. The files will be securely uploaded to
        Podonos service system.

        Args:
        path: Path to the audio file to evaluate. Must be set for single file eval like NMOS.
        path1: Path to the audio file to evaluate. If this is set, path2 must be set. For pairwise files like SMOS.
        path2: Path to the audio file to evaluate. If this is set, path1 must be set. For pairwise files like SMOS.
        tag: A comma separated list of string tags for path. Optional.
        tag1: A comma separated list of string tags for path1. Optional.
        tag2: A comma separated list of string tags for path2. Optional.

        Example:
        If you want to evaluate each audio file separately (e.g., naturalness MOS):
            add_file(path='/a/b/0.wav')

        If you want to evaluate a pair of audio files (e.g., preferences or similarity MOS):
            add_file(path0='/a/b/0-0.wav', path1='/a/b/0-1.wav')

        If you want to evaluate a triple of audio files (e.g., comparative similarity MOS):
            add_file(path0='/a/b/0-ref.wav', path1='/a/b/0-0.wav', path2='/a/b/0-1.wav')

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        # Check the input parameters.
        audio_json = {}
        if 'NMOS' == self._eval_config['_eval_type']:
            if 'path' not in kwargs:
                raise ValueError(f'"path" must be set for the evaluation type {self._eval_config["_eval_type"]}')
            path0 = kwargs['path']
            path_base0 = os.path.basename(path0)
            assert os.path.isfile(path0), f"File {path0} doesn't exist"
            assert os.access(path0, os.R_OK), f"File {path0} isn't readable"
            remote_object_name = os.path.join(self._api_key, self._eval_config['_eval_creation_timestamp'], path_base0)
            log.debug(f'remote_object_name: {remote_object_name}\n')
            nchannels0, framerate0, duration_in_ms0 = get_audio_info(path0)
            audio_json['name0'] = path_base0
            audio_json['nchannels0'] = nchannels0
            audio_json['framerate0'] = framerate0
            audio_json['duration_in_ms0'] = duration_in_ms0

        if 'SMOS' == self._eval_config['_eval_type']:
            if 'path' in kwargs:
                raise ValueError(f'"path" must not be set for the evaluation type {self._eval_config["_eval_type"]}')
            if 'path0' or 'path1' not in kwargs:
                raise ValueError(f'Both "path0" and "path1" must be set for the evaluation type {self._eval_config["_eval_type"]}')
            path0 = kwargs['path0']
            path1 = kwargs['path1']
            path_base0 = os.path.basename(path0)
            path_base1 = os.path.basename(path1)
            assert os.path.isfile(path0), f"File {path0} doesn't exist"
            assert os.path.isfile(path1), f"File {path1} doesn't exist"
            assert os.access(path0, os.R_OK), f"File {path0} isn't readable"
            assert os.access(path1, os.R_OK), f"File {path1} isn't readable"
            remote_object_name0 = os.path.join(self._api_key, self._eval_config['_eval_creation_timestamp'], path_base0)
            remote_object_name1 = os.path.join(self._api_key, self._eval_config['_eval_creation_timestamp'], path_base1)
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

        if 'tag' in kwargs:
            audio_json['tag'] = kwargs['tag']

        # Get the presigned URL for filename
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
        #log.debug(f'Presigned URL: {presigned_url}\n')

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
        audio_json['uploadStartAt'] = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
        try:
            r = requests.put(presigned_url,
                             data=open(path, 'rb'),
                             headers=upload_headers
                             )
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        time.sleep(0.1)
        # Timestamp in ISO 8601.
        audio_json['uploadFinishAt'] = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
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
        session_json = {'name': self._eval_name,
                        'id': self._eval_id,
                        'desc': self._eval_desc,
                        'type': self._eval_type,
                        'language': self._eval_language,
                        'num_eval': self._num_eval,
                        'expected_due': self._eval_expected_due,
                        'expected_due_tzname': self._eval_expected_due_tzname,
                        'createdAt': self._eval_creation_timestamp,
                        'files': self._eval_audio_json}

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._api_key, self._eval_creation_timestamp,
                                          os.path.basename('session.json'))
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
        # TODO: check r
        result_obj = {'status': 'ok'}

        # for i in progressbar(range(15), "Uploading: ", 40):
        #     time.sleep(0.04)
        print(f'Upload finished. You will receive en email once the evaluation is done.')
        # Initialize variables.
        self._init_eval_variables()

        return result_obj
