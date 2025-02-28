from dataclasses import dataclass, field
from typing import Optional, List
from podonos.common.enum import QuestionResponseCategory, QuestionUsageType, QuestionRelatedModel


@dataclass
class QuestionMetadataPosition:
    left: str = field(default_factory=str)
    right: str = field(default_factory=str)

    def to_dict(self) -> dict:
        return {"left": self.left, "right": self.right}


@dataclass
class QuestionMetadataLinearScale:
    title: Optional[str] = None
    label_text: QuestionMetadataPosition = field(default_factory=QuestionMetadataPosition)
    label_uri: Optional[QuestionMetadataPosition] = None


@dataclass
class QuestionMetadataColumn:
    linear_scale: QuestionMetadataLinearScale = field(default_factory=QuestionMetadataLinearScale)

    def to_dict(self) -> dict:
        return {
            "linear_scale": {
                "title": self.linear_scale.title,
                "label_text": self.linear_scale.label_text.to_dict(),
                "label_uri": self.linear_scale.label_uri.to_dict() if self.linear_scale.label_uri else None,
            }
        }


@dataclass
class TemplateOption:
    value: str
    label_text: Optional[str] = None
    label_uri: Optional[str] = None
    order: int = 0
    id: Optional[str] = None
    reference_file: Optional[str] = None

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
    related_model: Optional[QuestionRelatedModel] = None
    meta_data: Optional[QuestionMetadataColumn] = None
    options: List[TemplateOption] = field(default_factory=list)
    reference_file: Optional[str] = None
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
            "related_model": self.related_model.value if self.related_model else None,
            "meta_data": self.meta_data.to_dict() if self.meta_data else None,
        }

    def to_option_bulk_request(self) -> dict:
        return {"template_question_id": self.id, "options": [opt.to_dict() for opt in (self.options or [])]}
