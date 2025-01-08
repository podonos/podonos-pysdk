from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from podonos.common.enum import Language


@dataclass
class Template:
    id: str
    code: str
    title: str
    description: Optional[str]
    batch_size: int
    language: Language
    created_time: datetime
    updated_time: datetime

    @staticmethod
    def from_dict(data: dict) -> "Template":
        required_keys = required_keys = ["id", "code", "title", "batch_size", "language", "created_time", "updated_time"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for Evaluation: {data}")

        return Template(
            id=data["id"],
            code=data["code"],
            title=data["title"],
            description=data["description"],
            batch_size=data["batch_size"],
            language=Language.from_value(data["language"]),
            created_time=datetime.fromisoformat(data["created_time"].replace("Z", "+00:00")),
            updated_time=datetime.fromisoformat(data["updated_time"].replace("Z", "+00:00")),
        )
