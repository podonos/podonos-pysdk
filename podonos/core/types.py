from dataclasses import dataclass, field
from typing import Optional, List
from podonos.common.enum import QuestionResponseCategory, QuestionUsageType


@dataclass
class TemplateOption:
    value: str
    label_text: Optional[str] = None
    label_uri: Optional[str] = None
    order: int = 0
    id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "value": self.value, "label_text": self.label_text, "label_uri": self.label_uri, "order": self.order}


@dataclass
class TemplateQuestion:
    title: str
    response_category: QuestionResponseCategory
    usage_type: QuestionUsageType
    description: Optional[str] = None
    order: int = 0
    scale: int = 0
    has_other: bool = False
    has_none: bool = False
    options: List[TemplateOption] = field(default_factory=list)
    id: Optional[str] = None

    def to_create_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "response_category": self.response_category.value,
            "usage_type": self.usage_type.value,
            "scale": self.scale,
            "order": self.order,
            "has_other": self.has_other,
            "has_none": self.has_none,
        }

    def to_option_bulk_request(self) -> dict:
        return {"template_question_id": self.id, "options": [opt.to_dict() for opt in (self.options or [])]}
