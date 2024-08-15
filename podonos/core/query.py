import logging
from typing import Optional, Any

# Configure basic logging settings
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# Define a Question class to represent a question with a title and an optional description
class Question:
    _title: str
    _description: Optional[str]

    def __init__(self, title: str, description: Optional[str]):
        self._title = title
        self._description = description

    @property
    def title(self) -> str:
        return self._title

    @property
    def description(self) -> Optional[str]:
        return self._description

    def to_dict(self) -> "dict[str, Any]":  # type: ignore
        return {"title": self._title, "description": self._description}


# Define a Query class that encapsulates a Question object and a Option object in the future
class Query:
    _question: Question

    def __init__(self, question: Question):
        self._question = question

    @property
    def question(self) -> Question:
        return self._question

    @property
    def title(self) -> str:
        return self._question.title

    @property
    def description(self) -> Optional[str]:
        return self._question.description

    def to_dict(self) -> "dict[str, Any]":  # type: ignore
        return {"question": self._question.to_dict()}
