from dataclasses import dataclass
from typing import List


@dataclass
class ScriptCreateRequestDto:
    collection_id: str
    texts: List[str]

    def to_create_request_dto(self) -> dict:
        return {
            "collection_id": self.collection_id,
            "texts": self.texts,
        }

    @staticmethod
    def from_dict(collection_id: str, texts: List[str]) -> "ScriptCreateRequestDto":
        if len(collection_id) == 0:
            raise ValueError("The collection_id is required")

        if not texts or len(texts) == 0:
            raise ValueError("At least one text is required")

        for text in texts:
            if len(text) == 0:
                raise ValueError("The text is not allowed to be empty")

        return ScriptCreateRequestDto(
            collection_id=collection_id,
            texts=texts,
        )
