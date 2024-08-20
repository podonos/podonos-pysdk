from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Evaluation:
    id: str
    title: str
    internal_name: Optional[str]
    description: Optional[str]
    status: str
    created_time: datetime
    updated_time: datetime

    @staticmethod
    def from_dict(data: dict) -> "Evaluation":
        required_keys = ["id", "title", "status", "created_time", "updated_time"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for Evaluation: {data}")

        return Evaluation(
            id=data["id"],
            title=data["title"],
            internal_name=data["internal_name"],
            description=data["description"],
            status=data["status"],
            created_time=datetime.fromisoformat(data["created_time"].replace("Z", "+00:00")),
            updated_time=datetime.fromisoformat(data["updated_time"].replace("Z", "+00:00")),
        )

    def to_dict(self) -> dict:
        created_time_str = self.created_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        updated_time_str = self.updated_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return {
            "id": self.id,
            "title": self.title,
            "internal_name": self.internal_name,
            "description": self.description,
            "status": self.status,
            "created_time": created_time_str,
            "updated_time": updated_time_str,
        }
