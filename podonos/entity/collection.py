from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from podonos.common.enum import CollectionCustomerStatus, Language, CollectionTarget


@dataclass
class CollectionEntity:
    id: str
    name: str
    description: Optional[str]
    language: str
    num_required_people: int
    target: CollectionTarget
    started_time: Optional[datetime]
    ended_time: Optional[datetime]
    status: CollectionCustomerStatus
    created_time: datetime
    updated_time: datetime

    @staticmethod
    def from_dict(data: dict) -> "CollectionEntity":
        return CollectionEntity(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            language=data["language"],
            num_required_people=data["num_required_people"],
            target=CollectionTarget(data["target"]),
            started_time=data["started_time"],
            ended_time=data["ended_time"],
            status=CollectionCustomerStatus(data["customer_status"]),
            created_time=data["created_time"],
            updated_time=data["updated_time"],
        )
