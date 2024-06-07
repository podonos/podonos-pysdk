from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class EvaluationInformation:
    id: str
    project_id: str
    title: str
    introduction: str
    internal_name: Optional[str]
    description: Optional[str]
    status: str
    created_time: datetime
    updated_time: datetime

    @staticmethod
    def from_dict(data: dict) -> 'EvaluationInformation':
        if "id" not in data or "project_id" not in data or "title" not in data or "introduction" not in data or "status" not in data or "created_time" not in data or "updated_time" not in data:
            raise ValueError(f"Invalid data format for EvaluationInformation: {data}")
        
        return EvaluationInformation(
            id=data['id'],
            project_id=data['project_id'],
            title=data["title"],
            introduction=data["introduction"],
            internal_name=data["internal_name"],
            description=data["description"],
            status=data["status"],
            created_time=datetime.fromisoformat(data["created_time"].replace('Z', '+00:00')),
            updated_time=datetime.fromisoformat(data["updated_time"].replace('Z', '+00:00'))
        )