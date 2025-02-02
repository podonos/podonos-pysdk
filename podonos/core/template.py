from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from podonos.common.enum import (
    Language,
    QuestionResponseCategory,
    QuestionUsageType,
)

@dataclass
class TemplateOption:
    value: str
    label_text: Optional[str] = None
    order: int = 0
    id: Optional[str] = None
    label_uri: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "value": self.value,
            "label_text": self.label_text,
            "label_uri": self.label_uri,
            "order": self.order
        }

@dataclass
class TemplateQuestion:
    title: str
    response_category: QuestionResponseCategory
    usage_type: QuestionUsageType
    order: int
    description: Optional[str] = None
    scale: int = 0
    has_other: bool = False
    has_none: bool = False
    id: Optional[str] = None
    options: List[TemplateOption] = field(default_factory=list)

    def to_create_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "response_category": self.response_category.value,
            "usage_type": self.usage_type.value,
            "scale": self.scale,
            "order": self.order,
            "has_other": self.has_other,
            "has_none": self.has_none
        }

    def to_option_bulk_request(self) -> Dict[str, Any]:
        return {
            "template_question_id": self.id,
            "options": [opt.to_dict() for opt in self.options]
        }

@dataclass
class Template:
    """Template class for handling API responses"""
    id: Optional[str] = None
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    language: Optional[Language] = None
    batch_size: Optional[int] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    
    @staticmethod
    def from_api_response(data: dict) -> "Template":
        """Create Template instance from API response."""
        required_keys = ["id", "code", "title", "batch_size", "language", "created_time", "updated_time"]
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