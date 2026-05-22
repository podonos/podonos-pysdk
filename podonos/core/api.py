import podonos
import requests
import importlib.metadata
import time
import random
import math

from requests import Response
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError, ConnectTimeout, ReadTimeout
from typing import Dict, Any, Optional, Callable, Set, Tuple
from packaging.version import Version

from podonos.common.constant import *
from podonos.common.redaction import mask_secret, redact_secrets
from podonos.core.base import *
from podonos.common.validator import validate_args, Rules


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
    _retry_status_codes: Set[int]

    def __init__(
        self,
        api_key: str,
        api_url: str,
        max_retries: int = 5,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retry_status_codes: Optional[Set[int]] = None,
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
            raise ValueError(
                TerminalColor.FAIL
                + f"Invalid API key: {mask_secret(self._api_key)}"
                + TerminalColor.ENDC
            )
        return True

    @validate_args(key=Rules.str_non_empty, value=Rules.str_non_empty)
    def add_headers(self, key: str, value: str) -> None:
        self._headers[key] = value

    @validate_args(response=Rules.optional_instance_of(Response), exception=Rules.optional_instance_of(Exception))
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

    @validate_args(attempt=Rules.int_not_none)
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff with jitter."""
        delay = self._retry_delay * (self._backoff_factor**attempt)
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter

    def _format_retry_context(self, context: Optional[Dict[str, Any]]) -> str:
        """Format retry context without leaking secrets or signed URLs."""
        if not context:
            return ""

        safe_keys = [
            "method",
            "endpoint",
            "evaluation_id",
            "timeout",
            "batch_index",
            "batch_size",
            "batch_start",
            "file_count",
            "total_files",
            "external_endpoint",
        ]
        parts = [
            f"{key}={redact_secrets(context[key])}"
            for key in safe_keys
            if key in context
        ]
        return " ".join(parts)

    def _build_retry_context(
        self,
        context: Optional[Dict[str, Any]],
        **reserved: Any,
    ) -> Dict[str, Any]:
        """Merge caller context while keeping transport-owned keys authoritative."""
        request_context = dict(context or {})
        request_context.update(reserved)
        return request_context

    @staticmethod
    def _validate_timeout(timeout: Tuple[float, float]) -> Tuple[float, float]:
        """Validate public timeout values before they reach requests."""

        if not isinstance(timeout, (tuple, list)) or len(timeout) != 2:
            raise ValueError("timeout must be a (connect, read) tuple")

        normalized = []
        for value in timeout:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("timeout values must be positive numbers")
            if not math.isfinite(float(value)):
                raise ValueError("timeout values must be finite numbers")
            if value <= 0:
                raise ValueError("timeout values must be positive numbers")
            normalized.append(value)

        return normalized[0], normalized[1]

    def _sanitize_log_message(self, message: str) -> str:
        """Redact signed URL query strings and common secret-bearing fields."""
        return redact_secrets(message)

    def _execute_with_retry(
        self,
        request_func: Callable[[], Response],
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Execute a request function with retry logic."""
        last_exception = None
        context_str = self._format_retry_context(context)

        for attempt in range(self._max_retries + 1):
            try:
                response = request_func()

                # Check if we should retry based on status code
                if self._should_retry(response):
                    if attempt < self._max_retries:
                        delay = self._calculate_delay(attempt)
                        log.warning(
                            f"Request failed with status {response.status_code} "
                            f"{context_str}, retrying in {delay:.2f}s "
                            f"(attempt {attempt + 1}/{self._max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        log.error(
                            f"Request failed after {self._max_retries + 1} attempts "
                            f"with status {response.status_code} {context_str}"
                        )
                        response.raise_for_status()

                return response

            except (ConnectionError, Timeout, ConnectTimeout, ReadTimeout) as e:
                last_exception = e
                error_message = self._sanitize_log_message(str(e))
                if attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    log.warning(
                        f"Network error occurred {context_str}: {error_message}, "
                        f"retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{self._max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    log.error(
                        f"Network error after {self._max_retries + 1} attempts "
                        f"{context_str}: {error_message}"
                    )
                    raise
            except HTTPError as e:
                error_message = self._sanitize_log_message(str(e))
                # For HTTP errors, check if we should retry
                if self._should_retry(None, e) and attempt < self._max_retries:
                    delay = self._calculate_delay(attempt)
                    log.warning(
                        f"HTTP error occurred {context_str}: {error_message}, "
                        f"retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{self._max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    log.error(
                        f"HTTP error after {self._max_retries + 1} attempts "
                        f"{context_str}: {error_message}"
                    )
                    raise
            except RequestException as e:
                # For other request exceptions, don't retry
                log.error(f"Request exception {context_str}: {self._sanitize_log_message(str(e))}")
                raise

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        raise RequestException("Unknown error occurred during retry")

    @validate_args(endpoint=Rules.str_non_empty, params=Rules.dict_not_none_or_none, headers=Rules.dict_not_none_or_none)
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (5, 30),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        timeout = self._validate_timeout(timeout)
        request_header = self._headers if headers is None else headers
        request_context = self._build_retry_context(
            context,
            method="GET",
            endpoint=endpoint,
            timeout=timeout,
        )

        def make_request():
            return requests.get(f"{self._api_url}/{endpoint}", headers=request_header, params=params, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(endpoint=Rules.str_non_empty, data=Rules.dict_not_none, headers=Rules.dict_not_none_or_none)
    def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (5, 30),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        timeout = self._validate_timeout(timeout)
        request_header = self._headers if headers is None else headers
        request_context = self._build_retry_context(
            context,
            method="POST",
            endpoint=endpoint,
            timeout=timeout,
        )

        def make_request():
            return requests.post(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(endpoint=Rules.str_non_empty, data=Rules.dict_not_none, headers=Rules.dict_not_none_or_none)
    def put(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (5, 30),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        timeout = self._validate_timeout(timeout)
        request_header = self._headers if headers is None else headers
        request_context = self._build_retry_context(
            context,
            method="PUT",
            endpoint=endpoint,
            timeout=timeout,
        )

        def make_request():
            return requests.put(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(endpoint=Rules.str_non_empty, data=Rules.dict_not_none, headers=Rules.dict_not_none_or_none)
    def patch(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (5, 30),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        timeout = self._validate_timeout(timeout)
        request_header = self._headers if headers is None else headers
        request_context = self._build_retry_context(
            context,
            method="PATCH",
            endpoint=endpoint,
            timeout=timeout,
        )

        def make_request():
            return requests.patch(f"{self._api_url}/{endpoint}", headers=request_header, json=data, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(endpoint=Rules.str_non_empty, headers=Rules.dict_not_none_or_none)
    def delete(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (5, 30),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        timeout = self._validate_timeout(timeout)
        request_header = self._headers if headers is None else headers
        request_context = self._build_retry_context(
            context,
            method="DELETE",
            endpoint=endpoint,
            timeout=timeout,
        )

        def make_request():
            return requests.delete(f"{self._api_url}/{endpoint}", headers=request_header, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(
        url=Rules.str_non_empty, params=Rules.dict_not_none_or_none, headers=Rules.dict_not_none_or_none, cookies=Rules.dict_not_none_or_none
    )
    def external_get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (10, 60),
        context: Optional[Dict[str, Any]] = None,
        allow_redirects: bool = True,
    ) -> Response:
        """Make a GET request to an external URL with retry logic."""
        timeout = self._validate_timeout(timeout)
        request_header = headers or {}
        request_context = self._build_retry_context(
            context,
            method="GET",
            external_endpoint="external_get",
            timeout=timeout,
        )

        def make_request():
            return requests.get(
                url,
                headers=request_header,
                params=params,
                cookies=cookies,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )

        return self._execute_with_retry(make_request, request_context)

    @validate_args(url=Rules.str_non_empty, json_data=Rules.dict_not_none_or_none, headers=Rules.dict_not_none_or_none)
    def external_put(
        self,
        url: str,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (10, 120),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Make a PUT request to an external URL with retry logic."""
        timeout = self._validate_timeout(timeout)
        request_header = headers or {}
        request_context = self._build_retry_context(
            context,
            method="PUT",
            external_endpoint="presigned_put",
            timeout=timeout,
        )

        data_initial_position: Optional[int] = None
        if data is not None and hasattr(data, "tell") and hasattr(data, "seek"):
            try:
                data_initial_position = data.tell()
            except Exception:
                data_initial_position = None

        def make_request():
            if json_data is not None:
                return requests.put(url, headers=request_header, json=json_data, timeout=timeout)
            else:
                if data_initial_position is not None:
                    data.seek(data_initial_position)
                return requests.put(url, headers=request_header, data=data, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

    @validate_args(url=Rules.str_non_empty, json_data=Rules.dict_not_none_or_none, headers=Rules.dict_not_none_or_none)
    def external_post(
        self,
        url: str,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = (10, 60),
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        """Make a POST request to an external URL with retry logic."""
        timeout = self._validate_timeout(timeout)
        request_header = headers or {}
        request_context = self._build_retry_context(
            context,
            method="POST",
            external_endpoint="external_post",
            timeout=timeout,
        )

        def make_request():
            if json_data is not None:
                return requests.post(url, headers=request_header, json=json_data, timeout=timeout)
            else:
                return requests.post(url, headers=request_header, data=data, timeout=timeout)

        return self._execute_with_retry(make_request, request_context)

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
