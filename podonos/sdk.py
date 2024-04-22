"""Podonos SDK for speech/audio evaluation.
For details, please refer to https://github.com/podonos/pysdk/
"""

import datetime
import time

from podonos.constant import *
from podonos.default_config import DefaultConfig
from podonos.evaluator import Evaluator
from podonos.eval_name import *
from podonos.version import *

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def progressbar(it, prefix="", size=60):
    count = len(it)
    start = time.time()

    def show(j):
        x = int(size * j / count)
        remaining = ((time.time() - start) / j) * (count - j)

        mins, sec = divmod(remaining, 60)
        time_str = f"{int(mins):02}:{sec:05.2f}"

        print(f"{prefix}[{u'█' * x}{('.' * (size - x))}] Est wait {time_str}", end='\r',
              flush=True)

    for i, item in enumerate(it):
        yield item
        show(i + 1)
    print("\n", flush=True)


class EvalClient:
    """Evaluation client class. Used for creating individual evaluator."""

    _initialized = None
    _api_key = None
    _api_base_url = None

    _eval_id = None
    _eval_name = None
    _eval_desc = None
    _eval_type = None
    _eval_language = None
    _num_eval = 5
    _eval_expected_due = None
    _eval_expected_due_tzname = None
    _eval_creation_timestamp = None

    _eval_audio_json = []

    def __init__(self, api_key, api_base_url):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._initialized = True

    def create_evaluator(self, **kwargs) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.

        Args:
            name: This session name. Its length must be > 1. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. One of {'NMOS', 'EMOS'}. Default: NMOS
            lan: Human language for this audio. One of {'en-us', 'audio'}. Default: en-us
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 3.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                      Must be >= 12. Default: 12.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        # Mission name
        if 'name' not in kwargs:
            self._eval_name = generate_random_eval_name()
        else:
            self._eval_name = kwargs['name']
        if len(self._eval_name) <= 1:
            raise ValueError('"name" must be longer than 1.')
        log.debug(f'Name: {self._eval_name}')

        # Mission description
        if 'desc' not in kwargs:
            self._eval_desc = ""
        else:
            self._eval_desc = kwargs['desc']
        log.debug(f'Desc: {self._eval_desc}')

        # Evaluation type
        if 'type' not in kwargs:
            self._eval_type = 'NMOS'
        else:
            self._eval_type = kwargs['type']
        # Currently we support one evaluation type in one session.
        # TODO: Support multiple evaluation types in a single session.
        if self._eval_type not in ['NMOS']:
            raise ValueError('"type" must be one NMOS for now.')
        log.debug(f'Language: {self._eval_type}')

        # Language
        if 'language' not in kwargs:
            self._eval_language = 'en-us'
        else:
            self._eval_language = kwargs['language']

        if self._eval_language not in ['en-us']:
            raise ValueError('"language" must be {en-us}')
        log.debug(f'Language: {self._eval_language}')

        # Num eval per sample
        if 'num_eval' not in kwargs:
            self._num_eval = DefaultConfig.NUM_EVAL
        else:
            self._num_eval = int(kwargs['num_eval'])
        if self._num_eval < 1:
            raise ValueError(f'"num_eval" must be >= 1.')
        log.debug(f'num_eval: {self._num_eval}')

        # Expected due
        if 'due_hours' not in kwargs:
            # In 12 hours.
            due_hours = DefaultConfig.DUE_HOURS
        else:
            due_hours = int(kwargs['due_hours'])
        # TODO: allow floating point hours, e.g. 0.5.
        if due_hours < 1:
            raise ValueError('"due_hours" must be >=1.')
        due = datetime.datetime.now().astimezone() + datetime.timedelta(hours=due_hours)

        # Due string in RFC 3339.
        self._eval_expected_due = due.strftime('%Y%m%dT%H:%M:%S%z')
        self._eval_expected_due_tzname = datetime.datetime.now().astimezone().tzname()
        log.debug(f'Expected due: {self._eval_expected_due} {self._eval_expected_due_tzname}')
        # print(f'Expected due: {self._eval_expected_due} {self._eval_expected_due_tzname}')

        # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
        current_timestamp = datetime.datetime.today()
        self._eval_creation_timestamp = current_timestamp.strftime('%Y%m%dT%H%M%S')
        # We use the timestamp as a unique evaluation ID.
        # TODO create more human readable eval ID.
        self._eval_id = self._eval_creation_timestamp
        log.debug(f'Evaluation ID: {self._eval_id}')
        etor = Evaluator(self._api_key, self._api_base_url, self._eval_id,
                         self._eval_name, self._eval_desc, self._eval_type,
                         self._eval_language, self._num_eval, self._eval_expected_due,
                         self._eval_expected_due_tzname, self._eval_creation_timestamp)
        return etor


class Podonos:
    """Class for Podonos SDK."""
    _initialized = False

    @staticmethod
    def init(api_key: str,
             api_base_url: str = PODONOS_API_BASE_URL) -> EvalClient:
        """Initializes the SDK. This function must be called before calling other functions.
           Raises exception on invalid or missing API key. Also, raises exception on other failures.
           Returns: None

           Raises: ValueError: if the API Key is not set or invalid.
        """
        if not api_key:
            raise ValueError(f"Podonos API key is missing. Please visit {PODONOS_HOME}.")

        # If this is initialized multiple times, it sounds suspicious.
        if Podonos._initialized:
            log.debug('You are initializing >1 times.')

        # Check the minimum required package version.
        min_required_package_version = get_min_required_version(PODONOS_API_BASE_URL)
        assert check_min_required_version(min_required_package_version)

        # API key verification.
        if len(api_key) <= 3:
            raise ValueError(f"The API key {api_key} is not valid. "
                             f"Please use a valid API key or visit {PODONOS_HOME}.")

        Podonos._api_key = api_key
        Podonos._api_base_url = api_base_url

        headers = {
            'x-api-key': Podonos._api_key
        }
        response = requests.get(f'{Podonos._api_base_url}/clients/verify', headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        # Successfully initialized.
        Podonos._initialized = True

        client = EvalClient(Podonos._api_key, Podonos._api_base_url)
        return client
