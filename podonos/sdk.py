"""Podonos SDK for speech/audio evaluation.
For details, please refer to https://github.com/podonos/pysdk/
"""

import os
import time
import logging
from typing import Optional

from podonos.common.constant import *
from podonos.core.api import APIClient
from podonos.core.client import Client

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class Podonos:
    """Class for Podonos SDK."""

    _api_client: APIClient
    _initialized: bool = False

    @staticmethod
    def init(api_key: Optional[str] = None, api_url: str = PODONOS_API_BASE_URL) -> Client:
        """Initializes the SDK. This function must be called before calling other functions.
        Raises error on invalid or missing API key. Also, raises exception on other failures.
        api_key: API Key. If not set, try to read PODONOS_API_KEY. If both are not set, raises an error. Optional.
        api_url: URL for API access. Optional.

        Returns: None

        Raises: ValueError: if neither the API Key nor PODONOS_API_KEY is not set or invalid.
        """

        # If this is initialized multiple times, it sounds suspicious.
        if Podonos._initialized:
            log.debug("You are initializing >1 times.")

        api_key_env = os.environ.get(PODONOS_API_KEY, None)

        final_api_key = api_key or api_key_env
        if not final_api_key:
            raise ValueError(
                TerminalColor.FAIL + f"Podonos API key is missing. Please set api_key or "
                f"{PODONOS_API_KEY} environment variable.\n"
                f"For details, please visit {PODONOS_DOCS_API_KEY}." + TerminalColor.ENDC
            )

        if api_key and api_key_env:
            print(TerminalColor.WARN + f"Both api_key and {PODONOS_API_KEY} environment variable are set. " f"Uses api_key." + TerminalColor.FAIL)

        # API key verification.
        if len(final_api_key) <= 3:
            raise ValueError(
                TerminalColor.FAIL + f"The API key {final_api_key} is not valid. \n"
                f"Please use a valid API key or visit {PODONOS_HOME}." + TerminalColor.ENDC
            )

        api_client = APIClient(final_api_key, api_url)

        Podonos._api_client = api_client
        Podonos._initialized = api_client.initialize()
        return Client(api_client)
