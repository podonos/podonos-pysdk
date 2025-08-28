import podonos
import requests
import importlib.metadata
import time
import random

from requests import Response
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError, ConnectTimeout, ReadTimeout
from typing import Dict, Any, Optional, Callable
from packaging.version import Version

from podonos.common.constant import *
from podonos.core.base import *


class APIVersion:
    _minimum: Version
    _recommended: Version
    _latest: Version

    def __init__(self, minimum: str, recommended: str, latest: str):
        self._minimum = Version(minimum)
        self._recommended = Version(recommended)
        self._latest = Version(latest)

    @property
    def minimum(self) -> Version:
        return self._minimum

    @property
    def recommended(self) -> Version:
        return self._recommended

    @property
    def latest(self) -> Version:
        return self._latest


class APIClient:
    _api_key: str
    _api_url: str
    _headers: Dict[str, str] = {}
    _max_retries: int
    _retry_delay: float
    _backoff_factor: float
    _retry_status_codes: set

    def __init__(
        self,
        api_key: str,
        api_url: str,
        max_retries: int = 5,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retry_status_codes: Optional[set] = None,
    ):
        self._api_key = api_key
        self._api_url = api_url
        self._headers = {"X-API-KEY": self._api_key}
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._backoff_factor = backoff_factor
        self._retry_status_codes = retry_status_codes or {500, 502, 503, 504, 429, 408}

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def api_url(self) -> str:
        return self._api_url

    def initialize(self) -> bool:
        self._check_minimum_version()

        response = self.patch("api-keys/last-used-time", headers=self._headers, data={})
        if response.text != "true":
            raise ValueError(TerminalColor.FAIL + f"Invalid API key: {self._api_key}" + TerminalColor.ENDC)
        return True

    def add_headers(self, key: str, value: str) -> None:
        log.check_notnone(key)
        log.check_ne(key, "")
        log.check_notnone(value)
        self._headers[key] = value

    def _should_retry(self, response: Optional[Response], exception: Optional[Exception] = None) -> bool:
        """Determine if a request should be retried based on response or exception."""
        if exception is not None:
            # Retry on network-related exceptions
            if isinstance(exception, (ConnectionError, Timeout, ConnectTimeout, ReadTimeout)):
                return True
            # For HTTP errors, check if the status code should be retried
            if isinstance(exception, HTTPError) and hasattr(exception, "response") and exception.response is not None:
                return exception.response.status_code in self._retry_status_codes
            return False

        # Retry on specific HTTP status codes
        if response is not None:
            return response.status_code in self._retry_status_codes
        return False

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff with jitter."""
        delay = self._retry_delay * (self._backoff_factor**attempt)
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter

    def _execute_with_retry(self, request_func: Callable[[], Response]) -> Response:
        """Execute a request function with retry logic."""
        last_exception = None

        for attempt in range(self._max_retries + 1):
            try:
                response = request_func()

                # Check if we should retry based on status code
                if self._should_retry(response):
                    if attempt < self._max_retries:
                        delay = self._calculate_delay(attempt)
                        log.warning(
                            f"Request failed with status {response.status_code}, retrying in {delay:.2f}s (attempt {attempt + 1}/{self._max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        log.error(f"Request failed after {self._max_retries + 1} attempts with status {response.status_code}")
                        response.raise_for_status()

                return response

            except (ConnectionError, Timeout, ConnectTimeout, ReadTimeout) as e:
                last_exception = e
                if attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    log.warning(f"Network error occurred: {str(e)}, retrying in {delay:.2f}s (attempt {attempt + 1}/{self._max_retries + 1})")
                    time.sleep(delay)
                    continue
                else:
                    log.error(f"Network error after {self._max_retries + 1} attempts: {str(e)}")
                    raise
            except HTTPError as e:
                # For HTTP errors, check if we should retry
                if self._should_retry(None, e) and attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    log.warning(f"HTTP error occurred: {str(e)}, retrying in {delay:.2f}s (attempt {attempt + 1}/{self._max_retries + 1})")
                    time.sleep(delay)
                    continue
                else:
                    log.error(f"HTTP error after {self._max_retries + 1} attempts: {str(e)}")
                    raise
            except RequestException as e:
                # For other request exceptions, don't retry
                log.error(f"Request exception: {str(e)}")
                raise

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        raise RequestException("Unknown error occurred during retry")

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers

        def make_request():
            return requests.get(f"{self._api_url}/{endpoint}", headers=request_header, params=params, timeout=(5, 30))

        return self._execute_with_retry(make_request)

    def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers

        def make_request():
            return requests.post(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=(5, 30))

        return self._execute_with_retry(make_request)

    def put(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers

        def make_request():
            return requests.put(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=(5, 30))

        return self._execute_with_retry(make_request)

    def patch(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")

        request_header = self._headers if headers is None else headers

        def make_request():
            return requests.patch(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=(5, 30))

        return self._execute_with_retry(make_request)

    def delete(self, endpoint: str, headers: Optional[Dict[str, str]] = None) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")

        request_header = self._headers if headers is None else headers

        def make_request():
            return requests.delete(f"{self._api_url}/{endpoint}", headers=request_header, timeout=(5, 30))

        return self._execute_with_retry(make_request)

    def external_get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Response:
        """Make a GET request to an external URL with retry logic."""
        log.check_notnone(url)
        log.check_ne(url, "")
        request_header = headers or {}

        def make_request():
            return requests.get(url, headers=request_header, params=params, cookies=cookies, timeout=(10, 60))

        return self._execute_with_retry(make_request)

    def external_put(
        self,
        url: str,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        """Make a PUT request to an external URL with retry logic."""
        log.check_notnone(url)
        log.check_ne(url, "")
        request_header = headers or {}

        def make_request():
            if json_data is not None:
                return requests.put(url, headers=request_header, json=json_data, timeout=(10, 120))
            else:
                return requests.put(url, headers=request_header, data=data, timeout=(10, 120))

        return self._execute_with_retry(make_request)

    def external_post(
        self,
        url: str,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        """Make a POST request to an external URL with retry logic."""
        log.check_notnone(url)
        log.check_ne(url, "")
        request_header = headers or {}

        def make_request():
            if json_data is not None:
                return requests.post(url, headers=request_header, json=json_data, timeout=(10, 60))
            else:
                return requests.post(url, headers=request_header, data=data, timeout=(10, 60))

        return self._execute_with_retry(make_request)

    def _check_minimum_version(self) -> bool:
        response = self.get("version/sdk")
        api_version = APIVersion(**response.json())

        current_version = self._get_podonos_version()
        log.debug(f"current package version: {current_version}")

        if Version(current_version) >= api_version.recommended:
            return True

        if Version(current_version) >= api_version.minimum:
            print(
                "The current podonos package version is {current_version} "
                "while a newer version {api_version.latest} is available\n"
                "Please upgrade by 'pip install podonos --upgrade'"
            )
            return True

        # This version is lower than the minimum required version. Cannot proceed.
        print(
            TerminalColor.FAIL + f"The current podonos package version is {current_version} "
            f"while the minimum supported version is {api_version.minimum}"
            + TerminalColor.ENDC
            + "\n"
            + TerminalColor.BOLD
            + "Please upgrade"
            + TerminalColor.ENDC
            + f" by 'pip install podonos --upgrade'"
        )
        raise ValueError(f"Minimum supported version is {api_version.minimum}")

    @staticmethod
    def _get_podonos_version():
        try:
            # Try to get the version using importlib.metadata
            return importlib.metadata.version("podonos")
        except importlib.metadata.PackageNotFoundError:
            # Fallback to __version__ from podonos package if importlib fails
            return podonos.__version__
