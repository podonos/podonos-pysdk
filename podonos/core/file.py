import os
from typing import List, Optional, Tuple

from podonos.core.base import *


class File:
    _path: str
    _tags: List[str]
    _script: Optional[str]

    def __init__(self, path: str, model_tag: str, tags: List[str] = [], script: Optional[str] = None, is_ref: bool = False) -> None:
        """
        Args:
            path: Path to the file to evaluate. Required.
            model_tag: String that represents the model or group. Required.
            tags: A list of string for file. Optional.
            script: Script of the input audio in text. Optional.
            is_ref: True if this file is to be a reference for an evaluation type that requires a reference.
                    Optional. Default is False.
        """
        log.check_ne(path, "")
        log.check_ne(model_tag, "")

        self._path = self._validate_path(path)
        self._model_tag = self._validate_model_tag(model_tag)
        self._tags = self._set_tags(tags)
        self._script = self._validate_script(script)
        self._is_ref = self._validate_is_ref(is_ref)

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

    def _validate_path(self, path: str) -> str:
        """Validate file path exists and is readable.

        Args:
            path: File path to validate

        Returns:
            Validated path

        Raises:
            FileNotFoundError: If file doesn't exist or isn't readable
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} doesn't exist")

        if not os.access(path, os.R_OK):
            raise FileNotFoundError(f"File {path} isn't readable")

        return path

    def _validate_model_tag(self, model_tag: str) -> str:
        """Validate model_tag is a non-empty string.

        Args:
            model_tag: Model tag to validate

        Returns:
            Validated model tag

        Raises:
            ValueError: If model_tag is not a string or is empty
        """
        if not isinstance(model_tag, str):
            raise ValueError(f"model_tag must be a string, got {type(model_tag)}")
        if not model_tag:
            raise ValueError("model_tag cannot be empty")
        return model_tag

    def _validate_script(self, script: Optional[str]) -> Optional[str]:
        """Validate script is either None or a string.

        Args:
            script: Script to validate

        Returns:
            Validated script

        Raises:
            ValueError: If script is neither None nor a string
        """
        if script is not None and not isinstance(script, str):
            raise ValueError(f"script must be a string or None, got {type(script)}")
        return script

    def _validate_is_ref(self, is_ref: bool) -> bool:
        """Validate is_ref is a boolean.

        Args:
            is_ref: Boolean flag to validate

        Returns:
            Validated boolean flag

        Raises:
            ValueError: If is_ref is not a boolean
        """
        if not isinstance(is_ref, bool):
            raise ValueError(f"is_ref must be a boolean, got {type(is_ref)}")
        return is_ref

    def _set_tags(self, tags: List[str]) -> List[str]:
        """
        Set the tags as a list of unique strings for the file.

        Args:
            tags: A list of string for file.

        Returns:
            A list of unique tags

        Raises:
            ValueError: If tags is not a list or contains non-string elements
        """
        if not isinstance(tags, list):
            raise ValueError(f"tags must be a list, got {type(tags)}")

        unique_tags = []
        seen = set()
        for i, tag in enumerate(tags):
            if not isinstance(tag, (str, int, float)):
                raise ValueError(f"tag at index {i} must be a string, number, or boolean, got {type(tag)}")

            str_tag = str(tag)
            if str_tag not in seen:
                seen.add(str_tag)
                unique_tags.append(str_tag)

        return unique_tags
