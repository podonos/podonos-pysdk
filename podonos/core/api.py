import os
import podonos
import requests
import mimetypes
import importlib.metadata

from requests import Response
from typing import Dict, Any, Optional
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

    def __init__(self, api_key: str, api_url: str):
        self._api_key = api_key
        self._api_url = api_url
        self._headers = {"X-API-KEY": self._api_key}

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

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers
        response = requests.get(f"{self._api_url}/{endpoint}", headers=request_header, params=params)
        return response

    def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers
        response = requests.post(f"{self._api_url}/{endpoint}", headers=request_header, json=data)
        return response

    def put(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")
        request_header = self._headers if headers is None else headers
        response = requests.put(f"{self._api_url}/{endpoint}", headers=request_header, json=data)
        return response

    def patch(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")

        request_header = self._headers if headers is None else headers
        response = requests.patch(f"{self._api_url}/{endpoint}", headers=request_header, json=data)
        return response

    def delete(self, endpoint: str, headers: Optional[Dict[str, str]] = None) -> Response:
        log.check_notnone(endpoint)
        log.check_ne(endpoint, "")

        request_header = self._headers if headers is None else headers
        response = requests.delete(f"{self._api_url}/{endpoint}", headers=request_header)
        return response

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
