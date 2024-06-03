"""Podonos SDK for speech/audio evaluation.
For details, please refer to https://github.com/podonos/pysdk/
"""

import time
from typing import Optional

from podonos.common.constant import *
from podonos.common.enum import EvalType, Language
from podonos.core.client import Client
from podonos.core.config import EvalConfig
from podonos.evaluator import Evaluator
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


class EvalClient(Client):
    """Evaluation client class. Used for creating individual evaluator."""

    _eval_config: Optional[EvalConfig] = None
    
    def __init__(self, api_key: str, api_url: str):
        super().__init__(api_key, api_url)

    def create_evaluator(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalType.NMOS.value,
        lan: str = Language.EN_US.value,
        num_eval: int = 3,
        due_hours: int = 12
    ) -> Evaluator:
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

        self.eval_config = EvalConfig(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            num_eval=num_eval,
            due_hours=due_hours
        )
        etor = Evaluator(self._api_key, self._api_url, self._eval_config)
        return etor


class Podonos:
    """Class for Podonos SDK."""
    _initialized = False

    @staticmethod
    def init(
        api_key: str,
        api_base_url: str = PODONOS_API_BASE_URL
    ) -> EvalClient:
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
