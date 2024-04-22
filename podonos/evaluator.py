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

    _eval_id = None
    _eval_name = None
    _eval_desc = None
    _eval_type = None
    _eval_language = None
    _num_eval = DefaultConfig.NUM_EVAL
    _eval_expected_due = None
    _eval_expected_due_tzname = None
    _eval_creation_timestamp = None

    _eval_audio_json = []

    def __init__(self, key, base_url, eval_id, eval_name, eval_desc, eval_type,
                 eval_language, num_eval, expected_due, expected_due_tzname, creation_timestamp):
        self._api_key = key
        self._api_base_url = base_url
        self._eval_id = eval_id
        self._eval_name = eval_name
        self._eval_desc = eval_desc
        self._eval_type = eval_type
        self._eval_language = eval_language
        self._num_eval = num_eval
        self._eval_expected_due = expected_due
        self._eval_expected_due_tzname = expected_due_tzname
        self._eval_creation_timestamp = creation_timestamp
        self._initialized = True

    def _init_eval_variables(self):
        """Initializes the variables for one evaluation session."""
        self._initialized = False

        self._api_key = None
        self._api_base_url = None

        self._eval_id = None
        self._eval_name = None
        self._eval_desc = None
        self._eval_type = DefaultConfig.TYPE
        self._eval_language = DefaultConfig.LAN
        self._num_eval = DefaultConfig.NUM_EVAL
        self._eval_expected_due = None
        self._eval_expected_due_tzname = None
        self._eval_creation_timestamp = None

        self._eval_audio_json = []

    def add_file(self, **kwargs) -> None:
        """Adds new files for speech evaluation.
        The files may be either in {wav, mp3} format. The files will be securely uploaded to
        Podonos service system.

        Args:
            path (str): A path to the audio file to upload. Either in {wav, mp3}
            path1 (str, optional): A path to the audio file to upload. Either in {wav, mp3}
            path2 (str, optional): A path to the audio file to upload. Either in {wav, mp3}
            tag (str, optional): A comma separated list of string tags for the files to be added.
                You will conveniently organize the files with the given tags.

        Example:
            If you want to evaluate each audio file separately (e.g., naturalness MOS):
              add_file(filepath0='/a/b/0.wav')

            If you want to evaluate a pair of audio files (e.g., preferences test):
              add_file(filepath0='/a/b/0-0.wav', filepath1='/a/b/0-1.wav')

            If you want to evaluate a triple of audio files (e.g., comparative similarity MOS):
              add_file(filepath0='/a/b/0-ref.wav', filepath1='/a/b/0-0.wav', filepath1='/a/b/0-1.wav')

        Returns: None

        Raises:
            ValueError: if this function is called before calling init().
            FileNotFoundError: if a given file is not found.
        """

        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        # Check the input parameters.
        if 'path' not in kwargs:
            raise ValueError('"path" is not set')
        assert os.path.isfile(kwargs['path']), f"File {kwargs['path']} doesn't exist"
        assert os.access(kwargs['path'], os.R_OK), f"File {kwargs['path']} isn't readable"
        path = kwargs['path']
        path_base = os.path.basename(path)
        #remote_object_name = path_base
        remote_object_name = os.path.join(self._api_key, self._eval_creation_timestamp, path_base)
        log.debug(f'remote_object_name: {remote_object_name}\n')

        # if this is wav
        suffix = Path(path).suffix
        assert suffix == '.wav' or suffix == '.mp3',\
            f"Unsupported file format: {path}. We currently support wav or mp3 only."
        if suffix == '.wav':
            nchannels0, framerate0, duration_in_ms0 = get_wave_info(path)
        elif suffix == '.mp3':
            nchannels0, framerate0, duration_in_ms0 = get_mp3_info(path)

        audio_json = {
            'name': path_base,
            'nchannel': nchannels0,
            'framerate': framerate0,
            'duration_in_ms': duration_in_ms0
        }

        if 'tag' in kwargs:
            audio_json['tag'] = kwargs['tag']

        if 'filepath1' in kwargs:
            raise ValueError('"filepath1" is not supported yet. We will support soon.')

        if 'filepath2' in kwargs:
            raise ValueError('"filepath2" is not supported yet. We will support soon.')

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
