from typing import List, Optional

from podonos.core.base import *


class File:
    _path: str
    _tags: List[str]
    _script: Optional[str]

    def __init__(self, path: str, tags: List[str] = [], script: Optional[str] = None) -> None:
        """
        Args:
            path: Path to the file to evaluate.
            tags: A list of string for file. Optional.
            script: Script of the input audio in text. Optional.
        """
        log.check_ne(path, "")
        self._path = path
        self._tags = tags
        self._script = script

    @property
    def path(self) -> str:
        return self._path

    @property
    def tags(self) -> List[str]:
        return self._tags

    @property
    def script(self) -> Optional[str]:
        return self._script
