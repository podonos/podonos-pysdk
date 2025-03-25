from dataclasses import dataclass, field
from typing import Optional

from podonos.common.enum import CollectionTarget, Language


@dataclass
class CollectionCreateRequestDto:
    name: str
    description: Optional[str] = None
    language: str = field(default=Language.ENGLISH_AMERICAN.value)
    num_required_people: int = field(default=10)
    target: CollectionTarget = field(default=CollectionTarget.AUDIO)

    def get_language(self) -> Language:
        return Language(self.language)

    def to_create_request_dto(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "language": self.language,
            "num_required_people": self.num_required_people,
            "target": self.target.value,
        }

    @staticmethod
    def from_dict(
        name: str,
        description: Optional[str] = None,
        language: str = Language.ENGLISH_AMERICAN.value,
        num_required_people: int = 10,
        target: str = CollectionTarget.AUDIO.value,
    ) -> "CollectionCreateRequestDto":
        if len(name) == 0:
            raise ValueError("The name of the collection is required")

        if num_required_people < 1:
            raise ValueError("The number of required people must be greater than 0")

        if language != Language.ENGLISH_AMERICAN.value:
            raise ValueError("The language of the collection must be en-us")

        if target != CollectionTarget.AUDIO.value:
            raise ValueError("The target of the collection must be one of the following: AUDIO")

        return CollectionCreateRequestDto(
            name=name,
            description=description,
            language=Language.from_value(language).value,
            num_required_people=num_required_people,
            target=CollectionTarget.from_value(target),
        )
