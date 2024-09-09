from typing import List, Optional

from podonos.core.base import *


class File:
    _path: str
    _tags: List[str]
    _script: Optional[str]

    def __init__(self, path: str, model_tag: str, tags: List[str] = [], script: Optional[str] = None,
                 is_ref: bool = False) -> None:
        """
        Args:
            path: Path to the file to evaluate. Required.
            model_tag: String that represents the model or group. Required.
            tags: A list of string for file. Optional.
            script: Script of the input audio in text. Optional.
            is_ref: True if this file is to be a reference for an evaluation type that requires a reference.
                    Optiona. Default is False.
        """
        log.check_ne(path, "")
        log.check_ne(model_tag, "")
        self._path = path
        self._model_tag = model_tag
        self._tags = tags
        self._script = script
        self._is_ref = is_ref

    @property
    def path(self) -> str:
        return self._path

    @property
    def model_tag(self) -> str:
        return self._model_tag

    @property
    def tags(self) -> List[str]:
        return self._tags

    @property
    def script(self) -> Optional[str]:
        return self._script

    @property
    def is_ref(self) -> Optional[bool]:
        return self._is_ref
