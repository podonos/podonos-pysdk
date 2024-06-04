from typing import Optional

class Client:
    _api_key: str
    _api_url: str
    _initialized: bool = False
    
    def __init__(self, api_key: str, api_url: str):
        self._api_key = api_key
        self._api_url = api_url
        self._initialized = True
    
    @property
    def api_key(self) -> str:
        return self._api_key
    
    @property
    def api_url(self) -> str:
        return self._api_url