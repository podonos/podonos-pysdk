from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from podonos.common.enum import QuestionResponseCategory, QuestionUsageType, GuideCategory
from podonos.core.types import TemplateQuestion, TemplateOption


@dataclass
class Option:
    value: str
    label_text: Optional[str] = None
    order: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any], order: int = 0) -> "Option":
        if not data.get("value"):
            raise ValueError("Option must have a non-empty 'value' field")
        return cls(value=data["value"], label_text=data.get("label_text"), order=order)


class Question(ABC):
    def __init__(self, title: str, type: str, description: Optional[str] = None, order: int = 0):
        self.title = title
        self.type = type
        self.description = description
        self.order = order

    @abstractmethod
    def validate(self) -> None:
        """Validate the question details."""
        if not self.title:
            raise ValueError("Question must have a title")

    @abstractmethod
    def to_template_question(self) -> TemplateQuestion:
        """Convert to TemplateQuestion."""
        pass

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        """Create appropriate Question instance from dictionary."""
        question_type = data.get("type")
        if not question_type:
            raise ValueError("Question must have a type")

        question_map = {"SCORED": ScoredQuestion, "NON_SCORED": NonScoredQuestion, "COMPARISON": ComparisonQuestion, "GUIDE": GuideQuestion}

        if question_type not in question_map:
            raise ValueError(f"Unknown question type: {question_type}")

        return question_map[question_type].from_dict(data)


class ScoredQuestion(Question):
    def __init__(self, title: str, options: List[Option], description: Optional[str] = None, order: int = 0):
        super().__init__(title, "SCORED", description, order)
        self.options = options

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError("SCORED question must have options")

        # Validate that all option values are numbers
        for option in self.options:
            try:
                float(option.value)
            except ValueError:
                raise ValueError(f"SCORED question option value '{option.value}' must be a number")

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self.title,
            description=self.description,
            response_category=QuestionResponseCategory.CHOICE_ONE,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            options=[TemplateOption(value=opt.value, label_text=opt.label_text, order=i) for i, opt in enumerate(self.options)],
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoredQuestion":
        if "options" not in data or not data["options"]:
            raise ValueError("SCORED question must have options")

        options = [Option.from_dict(opt, order=i) for i, opt in enumerate(data["options"])]
        return cls(title=data["title"], description=data.get("description"), options=options, order=data.get("order", 0))


class NonScoredQuestion(Question):
    def __init__(
        self,
        title: str,
        options: List[Option],
        allow_multiple: bool,
        description: Optional[str] = None,
        has_other: bool = False,
        has_none: bool = False,
        order: int = 0,
    ):
        super().__init__(title, "NON_SCORED", description, order)
        self.options = options
        self.allow_multiple = allow_multiple
        self.has_other = has_other
        self.has_none = has_none

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError("NON_SCORED question must have options")

    def to_template_question(self) -> TemplateQuestion:
        response_category = QuestionResponseCategory.CHOICE_MULTI if self.allow_multiple else QuestionResponseCategory.CHOICE_ONE_NO_SCORE
        return TemplateQuestion(
            title=self.title,
            description=self.description,
            response_category=response_category,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            has_other=self.has_other,
            has_none=self.has_none,
            options=[TemplateOption(value=opt.value, label_text=opt.label_text, order=i) for i, opt in enumerate(self.options)],
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NonScoredQuestion":
        if "options" not in data or not data["options"]:
            raise ValueError("NON_SCORED question must have options")
        if "allow_multiple" not in data:
            raise ValueError("NON_SCORED question must specify allow_multiple")

        options = [Option.from_dict(opt, order=i) for i, opt in enumerate(data["options"])]
        return cls(
            title=data["title"],
            description=data.get("description"),
            options=options,
            allow_multiple=data["allow_multiple"],
            has_other=data.get("has_other", False),
            has_none=data.get("has_none", False),
            order=data.get("order", 0),
        )


class ComparisonQuestion(Question):
    def __init__(self, title: str, scale: int = 5, description: Optional[str] = None, order: int = 0):
        super().__init__(title, "COMPARISON", description, order)
        self.scale = scale

    def validate(self) -> None:
        super().validate()
        if self.scale < 2 or self.scale > 9:
            raise ValueError("COMPARISON question scale must be between 2 and 9")

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self.title,
            description=self.description,
            response_category=QuestionResponseCategory.SCALE_LINEAR,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            scale=self.scale,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComparisonQuestion":
        return cls(title=data["title"], description=data.get("description"), scale=data.get("scale", 5), order=data.get("order", 0))


class GuideQuestion(Question):
    def __init__(self, title: str, category: GuideCategory, description: Optional[str] = None, order: int = 0):
        super().__init__(title, "GUIDE", description, order)
        self.category = category

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.category, GuideCategory):
            raise ValueError("GUIDE question must have a valid category")

    def to_template_question(self) -> TemplateQuestion:
        # Map GuideCategory to QuestionUsageType
        usage_type_map = {
            GuideCategory.CORRECT: QuestionUsageType.GUIDELINE_CORRECT,
            GuideCategory.WARNING: QuestionUsageType.GUIDELINE_WARNING,
            GuideCategory.PROHIBIT: QuestionUsageType.GUIDELINE_PROHIBIT,
        }

        return TemplateQuestion(
            title=self.title,
            description=self.description,
            response_category=QuestionResponseCategory.INSTRUCTION,
            usage_type=usage_type_map[self.category],
            order=self.order,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuideQuestion":
        if "category" not in data:
            raise ValueError("GUIDE question must specify category")

        try:
            category = GuideCategory(data["category"])
        except ValueError:
            raise ValueError(f"Invalid guide category: {data['category']}")

        return cls(title=data["title"], description=data.get("description"), category=category, order=data.get("order", 0))
