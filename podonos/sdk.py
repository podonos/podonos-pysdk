"""Podonos SDK for speech/audio evaluation.
For details, please refer to https://github.com/podonos/pysdk/
"""

import time

from podonos.common.constant import *
from podonos.core.client import Client
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

        print(f"{prefix}[{u'█' * x}{('.' * (size - x))}] Est wait {time_str}", end='\r', flush=True)

    for i, item in enumerate(it):
        yield item
        show(i + 1)
    print("\n", flush=True)

class Podonos:
    """Class for Podonos SDK."""
    _api_key: str
    _api_base_url: str
    _initialized: bool = False

    @staticmethod
    def init(
        api_key: str,
        api_base_url: str = PODONOS_API_BASE_URL
    ) -> Client:
        """ Initializes the SDK. This function must be called before calling other functions.
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
            raise ValueError(
                f"The API key {api_key} is not valid. \n"
                f"Please use a valid API key or visit {PODONOS_HOME}."
            )

        Podonos._api_key = api_key
        Podonos._api_base_url = api_base_url

        headers = {
            'x-api-key': Podonos._api_key
        }
        response = requests.get(f'{Podonos._api_base_url}/customers/verify/api-key', headers=headers)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError

        # Successfully initialized.
        Podonos._initialized = True
        return Client(Podonos._api_key, Podonos._api_base_url)
