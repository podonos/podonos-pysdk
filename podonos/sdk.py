"""Podonos SDK for speech/audio evaluation.
For details, please refer to https://github.com/podonos/pysdk/
"""

import datetime
import logging
import os
import requests
import warnings
import wave


# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Text colors on terminal
class bcolors:
    BOLD = '\033[1m'
    ENDC = '\033[0m'
    FAIL = '\033[91m'
    OK = '\033[92m'
    WARN = '\033[93m'


# Default configuration
class DefaultConfig:
    TYPE = 'NMOS'
    LAN = 'en-us'
    MIN_REPEAT = 3
    DUE_HOURS = 12


# Podonos contact email
_PODONOS_HOME = 'https://www.podonos.com/'

# Podonos API base URL
_PODONOS_API_BASE_URL = "https://prod.podonosapi.com"


def _get_wave_info(filepath):
    """ Gets info from a wave file.

    Returns:
        nchannels: Number of channels
        framerate: Number of frames per second. Same as the sampling rate.
        duration_in_ms: Total length of the audio in milliseconds

    Raises:
        FileNotFoundError: if the file is not found.
        wave.Error: if the file doesn't read properly.
    """
    wav = wave.open(filepath, "r")
    nchannels, sampwidth, framerate, nframes, comptype, compname = wav.getparams()
    assert comptype == 'NONE'
    duration_in_ms = int(nframes * 1000.0 / float(framerate))
    return nchannels, framerate, duration_in_ms


def _init_eval_variables():
    """Initializes the variables for one evaluation session."""
    _initialized = False

    _api_key = None
    _api_base_url = None

    _eval_id = None
    _eval_name = None
    _eval_desc = None
    _eval_type = DefaultConfig.TYPE
    _eval_language = DefaultConfig.LAN
    _eval_min_repeat = DefaultConfig.MIN_REPEAT
    _eval_expected_due = None
    _eval_expected_due_tzname = None
    _eval_creation_timestamp = None

    _eval_audio_json = []

class Evaluator:
    """Evaluator for a single type of evaluation session."""
    _initialized = False

    _api_key = None
    _api_base_url = None

    _eval_id = None
    _eval_name = None
    _eval_desc = None
    _eval_type = None
    _eval_language = None
    _eval_min_repeat = 5
    _eval_expected_due = None
    _eval_expected_due_tzname = None
    _eval_creation_timestamp = None

    _eval_audio_json = []

    @staticmethod
    def add_file(**kwargs) -> None:
      """Adds new files for speech evaluation.
      The files may be either in {wav, mp3} format. The files will be securely uploaded to
      Podonos service system.

      Args:
        filename0 (str): A path to the audio file to upload. Either in {wav, mp3}
        filename1 (str, optional): A path to the audio file to upload. Either in {wav, mp3}
        filename2 (str, optional): A path to the audio file to upload. Either in {wav, mp3}
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
      if not Podonos._initialized:
        raise ValueError("This function is called before calling init().")

      # Check the input parameters.
      if 'filepath0' not in kwargs:
        raise ValueError('"filepath0" is not set')
      assert os.path.isfile(kwargs['filepath0']), f"File {kwargs['filepath0']} doesn't exist"
      assert os.access(kwargs['filepath0'], os.R_OK), f"File {kwargs['filepath0']} isn't readable"
      filepath0 = kwargs['filepath0']
      filepath0_base = os.path.basename(filepath0)
      remote_object_name = os.path.join(Podonos._eval_creation_timestamp, filepath0_base)
      log.debug(f'remote_object_name: {remote_object_name}\n')

      nchannels0, framerate0, duration_in_ms0 = _get_wave_info(filepath0)
      audio_json = {
        'name': filepath0_base,
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

      # Get the presigned URL for filenam
      headers = {
        'x-api-key': Podonos._api_key
      }
      response = requests.get(f'{Podonos._api_base_url}/client/uploading-presigned-url?'
                              f'filename={remote_object_name}', headers=headers)
      if response.status_code != 200:
        raise requests.exceptions.HTTPError
      presigned_url = response.text
      log.debug(f'Presigned URL: {presigned_url}\n')

      # Upload the file.
      _, ext = os.path.splitext(filepath0)
      if ext == '.wav':
        upload_headers = {'Content-type': 'audio/wav'}
      elif ext == '.mp3':
        upload_headers = {'Content-type': 'audio/mpeg'}
      elif ext == '.json':
        upload_headers = {'Content-type': 'application/json'}

      # Timestamp in ISO 8601.
      audio_json['uploadStartAt'] = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
      try:
        r = requests.put(presigned_url,
                         data=open(filepath0, 'rb'),
                         headers=upload_headers
                         )
      except requests.exceptions.HTTPError as e:
        log.error(f"HTTP Error: {e}")

      # Timestamp in ISO 8601.
      audio_json['uploadFinishAt'] = datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
      Podonos._eval_audio_json.append(audio_json)


    def close(self):
        """Closes the file uploading and evaluation session.
        This function holds until the file uploading finishes.

        Returns:
            JSON object containing the uploading status.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before calling init().")

        # Create a json.
        session_json = {}
        session_json['name'] = self._eval_name
        session_json['id'] = self._eval_id
        session_json['desc'] = self._eval_desc
        session_json['type'] = self._eval_type
        session_json['language'] = self._eval_language
        session_json['min_repeat'] = self._eval_min_repeat
        session_json['expected_due'] = self._eval_expected_due
        session_json['expected_due_tzname'] = self._eval_expected_due_tzname
        session_json['createdAt'] = self._eval_creation_timestamp
        session_json['files'] = self._eval_audio_json

        # Get the presigned URL for filename
        remote_object_name = os.path.join(self._eval_creation_timestamp, os.path.basename('session.json'))
        headers = {
            'x-api-key': self._api_key
        }
        response = requests.get(f'{self._api_base_url}/client/uploading-presigned-url?'
                                f'filename={remote_object_name}', headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError
        presigned_url = response.text
        log.debug(f'Presigned URL: {presigned_url}\n')

        upload_headers = {'Content-type': 'application/json'}
        try:
            r = requests.put(presigned_url,
                             json=session_json,
                             headers=upload_headers
                             )
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error: {e}")
        # TODO: check r
        result_obj = {'status': 'ok'}

        # Initialize variables.
        _init_eval_variables()

        return result_obj


class EvalClient:
    """Evaluation client class. Used for creating individual evaluator."""
    _api_key = None
    _api_base_url = None

    _eval_id = None
    _eval_name = None
    _eval_desc = None
    _eval_type = None
    _eval_language = None
    _eval_min_repeat = 5
    _eval_expected_due = None
    _eval_expected_due_tzname = None
    _eval_creation_timestamp = None

    _eval_audio_json = []

    @staticmethod
    def create_evaluator(**kwargs) -> str:
        """Creates a new mission for speech evaluation.

        Args:
            name: This mission's name. Its length must be > 1.
            desc: Description of this mission. Optional.
            type: Evaluation type. One of {'NMOS', 'EMOS'}. Further coming. Default: NMOS
            lan: Human language for this audio. One of {'en-us'}. Further coming. Default: en-us
            min_repeat: The minimum number of repetition for each audio evaluation. Should be >=5. Default: 5.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                      Must be >= 1. Default: 7.

        Returns:
            Evaluator instance

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not EvalClient._initialized:
            raise ValueError("This function is called before initialization.")

        # Mission name
        if 'name' not in kwargs:
            raise ValueError('"name" is not set')
            EvalClient._eval_name = kwargs['name']
        if len(EvalClient._eval_name) < 2:
            raise ValueError('"name" must be >1.')
        log.debug(f'Name: {EvalClient._eval_name}')

        # Mission description
        if 'desc' not in kwargs:
            EvalClient._eval_desc = ""
        else:
            EvalClient._eval_desc = kwargs['desc']
        log.debug(f'Desc: {EvalClient._eval_desc}')

        # Evaluation type
        if 'type' not in kwargs:
            raise ValueError('"type" is not set')
        EvalClient._eval_type = kwargs['type']
        # Currently we support one evaluation type in one mission.
        # TODO: Support multiple evaluation types in a single mission.
        if EvalClient._eval_type not in ['NMOS']:
            raise ValueError('"type" must be one NMOS for now.')
        log.debug(f'Language: {EvalClient._eval_type}')

        # Language
        if 'language' not in kwargs:
            EvalClient._eval_language = 'en-us'
        else:
            EvalClient._eval_language = kwargs['language']

        if EvalClient._eval_language not in ['en-us']:
            raise ValueError('"language" must be {en-us}')
        log.debug(f'Language: {EvalClient._eval_language}')

        # Minimum repetition
        if 'min_repeat' not in kwargs:
            EvalClient._eval_min_repeat = DefaultConfig.MIN_REPEAT
        else:
            EvalClient._eval_min_repeat = int(kwargs['min_repeat'])
        if EvalClient._eval_min_repeat < DefaultConfig.MIN_REPEAT:
            raise ValueError(f'"min_repeat" must be >={DefaultConfig.MIN_REPEAT}.')
        log.debug(f'min_repeat: {EvalClient._eval_min_repeat}')

        # Expected due
        if 'due_hours' not in kwargs:
            # In 7 days.
            due_hours = DefaultConfig.DUE_HOURS
        else:
            due_hours = int(kwargs['due_hours'])
        # TODO: allow floating point hours, e.g. 0.5.
        if due_hours < 1:
            raise ValueError('"due_hours" must be >=1.')
        due = datetime.datetime.now().astimezone() + datetime.timedelta(hours=due_hours)
        # Due string in RFC 3339.
        EvalClient._eval_expected_due = due.strftime('%Y%m%dT%H:%M:%S%z')
        EvalClient._eval_expected_due_tzname = datetime.datetime.now().astimezone().tzname()
        log.debug(f'Expected due: {EvalClient._eval_expected_due} {EvalClient._eval_expected_due_tzname}')
        print(f'Expected due: {EvalClient._eval_expected_due} {EvalClient._eval_expected_due_tzname}')

        # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
        current_timestamp = datetime.datetime.today()
        EvalClient._eval_creation_timestamp = current_timestamp.strftime('%Y%m%dT%H%M%S')

        # TODO: create evaluator.
        EvalClient._eval_id = "NOT_IN_USE_YET"
        etor = Evaluator()
        return etor

class Podonos:
    """Class for Podonos SDK."""
    _initialized = False

    @staticmethod
    def init(api_key: str,
             api_base_url: str = _PODONOS_API_BASE_URL) -> None:
        """Initializes the SDK. This function must be called before calling other functions.
           Raises exception on invalid or missing API key. Also, raises exception on other failures.
           Returns: None

           Raises: ValueError: if the API Key is not set or invalid.
        """
        if not api_key:
            raise ValueError(f"Podonos API key is missing. Please visit {_PODONOS_HOME}.")

        # If this is initialized multiple times, it sounds suspicious.
        if Podonos._initialized:
            warnings.warn("Podonos SDK has already been initialized.")

        # TODO: Validate api_key properly
        if len(api_key) <= 3:
            raise ValueError(f"The API key {api_key} is not valid. "
                             f"Please use a valid API key or visit {_PODONOS_HOME}.")
        _init_eval_variables()

        Podonos._api_key = api_key
        Podonos._api_base_url = api_base_url

        headers = {
            'x-api-key': Podonos._api_key
        }
        response = requests.get(f'{Podonos._api_base_url}/client/verify', headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        # Successfully initialized.
        Podonos._initialized = True

        client = EvalClient()
        return client