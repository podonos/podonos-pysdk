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

    _api_key = None
    _api_base_url = None
    _initialized = None

    _eval_config = {}

    def __init__(self, api_key, api_base_url):
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._initialized = True

    def create_evaluator(self, **kwargs) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://docs.dyspatch.io/localization/supported_languages/

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. One of {'NMOS', 'SMOS', 'P808'}. Default: NMOS
            lan: Human language for this audio. One of {'en-us', 'ko-kr', 'audio'}. Default: en-us
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

        self._eval_config = {}

        # Mission name
        if 'name' not in kwargs:
            eval_name = generate_random_eval_name()
        else:
            if len(kwargs['name']) <= 1:
                raise ValueError('"name" must be longer than 1.')
            eval_name = kwargs['name']
        log.debug(f'Name: {eval_name}')
        self._eval_config['eval_name'] = eval_name

        # Mission description
        if 'desc' not in kwargs:
            eval_desc = ""
        else:
            eval_desc = kwargs['desc']
        log.debug(f'Desc: {eval_desc}')
        self._eval_config['eval_desc'] = eval_desc

        # Evaluation type
        if 'type' not in kwargs:
            eval_type = 'NMOS'
        else:
            eval_type = kwargs['type']
        # We support one evaluation type in one session.
        if eval_type not in ['NMOS', 'SMOS', 'P808']:
            raise ValueError(f'"type" must be one of {{NMOS, SMOS, P808}}. '
                             f'Do you want other evaluation types? Let us know at {PODONOS_CONTACT_EMAIL}.')
        log.debug(f'Eval type: {eval_type}')
        self._eval_config['eval_type'] = eval_type

        # Language
        if 'lan' not in kwargs:
            eval_language = 'en-us'
        else:
            eval_language = kwargs['lan']

        if eval_language not in ['en-us', 'ko-kr', 'audio']:
            raise ValueError(f'"lan" must be one of {{en-us, ko-kr, audio}}. '
                             f'Do you want us to support other languages? Let us know at {PODONOS_CONTACT_EMAIL}.')
        log.debug(f'Language: {eval_language}')
        self._eval_config['eval_lan'] = eval_language

        # Num eval per sample
        if 'num_eval' not in kwargs:
            num_eval = DefaultConfig.NUM_EVAL
        else:
            num_eval = int(kwargs['num_eval'])
        if num_eval < 1:
            raise ValueError(f'"num_eval" must be >= 1.')
        log.debug(f'num_eval: {num_eval}')
        self._eval_config['num_eval'] = num_eval

        # Expected due
        if 'due_hours' not in kwargs:
            # In 12 hours.
            due_hours = DefaultConfig.DUE_HOURS
        else:
            due_hours = int(kwargs['due_hours'])
        # TODO: allow floating point hours, e.g. 0.5.
        if due_hours < 12:
            raise ValueError('"due_hours" must be >=12.')
        utcnow = datetime.datetime.now()
        due = utcnow + datetime.timedelta(hours=due_hours)

        # Due string in ISO 8601.
        self._eval_config['eval_expected_due'] = due.astimezone().isoformat(timespec='milliseconds')
        self._eval_config['eval_expected_due_tzname'] = utcnow.astimezone().tzname()
        log.debug(f'Expected due: {self._eval_config["eval_expected_due"]} '
                  f'{self._eval_config["eval_expected_due_tzname"]}')

        # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
        current_timestamp = utcnow.astimezone()
        self._eval_config['eval_creation_timestamp'] = current_timestamp.isoformat(timespec='milliseconds')
        # We use the timestamp as a unique evaluation ID.
        # TODO create more human readable eval ID.
        self._eval_config['eval_id'] = self._eval_config['eval_creation_timestamp']
        log.debug(f'Evaluation ID: {self._eval_config["eval_id"]}')
        etor = Evaluator(self._api_key, self._api_base_url, self._eval_config)
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
        assert check_min_required_version(api_base_url)

        # API key verification.
        if len(api_key) <= 3:
            raise ValueError(f"The API key {api_key} is not valid. "
                             f"Please use a valid API key or visit {PODONOS_HOME}.")

        Podonos._api_key = api_key
        Podonos._api_base_url = api_base_url

        headers = {
            'x-api-key': Podonos._api_key
        }
        response = requests.get(f'{Podonos._api_base_url}/clients/verify/api-key', headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        # Successfully initialized.
        Podonos._initialized = True

        client = EvalClient(Podonos._api_key, Podonos._api_base_url)
        return client
