from typing import List

class File:
    _path: str
    _tags: List[str]
    
    def __init__(self, path: str, tags: List[str] = []) -> None:
        """
        Args:
            path: Path to the file to evaluate. Must be set for single file eval like NMOS.
            tag: A comma separated list of string tags for path. Optional.
        """
        self._path = path
        self._tags = tags
    
    @property
    def path(self) -> str:
        return self._path
    
    @property
    def tags(self) -> List[str]:
        return self._tags