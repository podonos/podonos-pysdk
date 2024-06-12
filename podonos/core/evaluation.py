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
        required_keys = ["id", "project_id", "title", "introduction", "status", "created_time", "updated_time"]
        for key in required_keys:
            if key not in data:
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
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "introduction": self.introduction,
            "internal_name": self.internal_name,
            "description": self.description,
            "status": self.status,
            "created_time": self.created_time,
            "updated_time": self.updated_time
        }