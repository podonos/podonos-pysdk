from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional, List, Dict, Any

from podonos.common.enum import QuestionResponseCategory, QuestionUsageType, InstructionCategory, QuestionRelatedModel
from podonos.core.types import QuestionMetadataColumn, QuestionMetadataLinearScale, QuestionMetadataPosition, TemplateQuestion, TemplateOption

TYPE_OF_OPTION_KEY = Literal["score", "label_text", "reference_file"]
TYPE_OF_QUESTION_KEY = Literal[
    "type",
    "question",
    "instruction",
    "description",
    "scale",
    "allow_multiple",
    "has_other",
    "has_none",
    "related_model",
    "order",
    "options",
    "reference_file",
    "anchor_label",
]


@dataclass
class Option:
    value: str
    label_text: Optional[str] = None
    order: int = 0
    reference_file: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_OPTION_KEY, Any], value: Optional[str] = None, order: int = 0, is_score: bool = True) -> "Option":
        if not data.get("label_text"):
            raise ValueError("Option must have a non-empty 'label_text' field")
        if not is_score:
            return cls(value=data["label_text"], order=order, reference_file=data.get("reference_file", None))
        if not value:
            raise ValueError("Score question's option must have a value")
        return cls(value=value, label_text=data.get("label_text"), order=order, reference_file=data.get("reference_file", None))


class Question(ABC):
    def __init__(self, title: str, type: str, batch_size: int, description: Optional[str] = None, order: int = 0):
        self.title = title  # title can be 'question' or 'instruction'
        self.type = type
        self.batch_size = batch_size
        self.description = description
        self.order = order

    @abstractmethod
    def validate(self) -> None:
        """Validate the question details."""
        if not self.title:
            raise ValueError("Question must have a 'question' or 'instruction'")

    @abstractmethod
    def to_template_question(self) -> TemplateQuestion:
        """Convert to TemplateQuestion."""
        pass

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_QUESTION_KEY, Any], batch_size: int) -> "Question":
        """Create appropriate Question instance from dictionary."""
        question_type = data.get("type")
        if not question_type:
            raise ValueError("Question must have a type")

        question_map = {
            "SCORED": ScoredQuestion,
            "NON_SCORED": NonScoredQuestion,
            "COMPARISON": ComparisonQuestion,
            InstructionCategory.DO.value: Instruction,
            InstructionCategory.WARNING.value: Instruction,
            InstructionCategory.DONT.value: Instruction,
        }

        if question_type not in question_map:
            raise ValueError(f"Unknown question type: {question_type} (must be one of {', '.join(question_map.keys())})")

        return question_map[question_type].from_dict(data, batch_size)


class ScoredQuestion(Question):
    def __init__(
        self,
        question: str,
        options: List[Option],
        related_model: QuestionRelatedModel,
        batch_size: int,
        description: Optional[str] = None,
        order: int = 0,
    ):
        super().__init__(question, "SCORED", batch_size, description, order)
        self.options = options
        self.related_model = related_model

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError("SCORED question must have options")

        if not QuestionRelatedModel.is_member(self.related_model.value) and self.batch_size > 1:
            raise ValueError(
                f"SCORED question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

        # Validate that all option values are numbers
        for option in self.options:
            try:
                float(option.value)
            except ValueError:
                raise ValueError(f"SCORED question option value '{option.value}' must be a number")

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self.title,  # question is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.CHOICE_ONE,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            related_model=self.related_model,
            options=[
                TemplateOption(value=opt.value, label_text=opt.label_text, order=i, reference_file=opt.reference_file)
                for i, opt in enumerate(self.options)
            ],
        )

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_QUESTION_KEY, Any], batch_size: int) -> "ScoredQuestion":
        if "options" not in data or not data["options"]:
            raise ValueError("SCORED question must have options")

        option_length = len(data["options"])
        if option_length < 1 or option_length > 9:
            raise ValueError("SCORED question must have between 1 and 9 options")

        related_model = (
            QuestionRelatedModel.from_value(data.get("related_model", QuestionRelatedModel.ALL.value)) if batch_size > 1 else QuestionRelatedModel.ALL
        )
        option_values = [str(score) for score in range(option_length, 0, -1)]
        options = [Option.from_dict(opt, value=option_values[i], order=i, is_score=True) for i, opt in enumerate(data["options"])]
        return cls(
            question=data["question"],
            description=data.get("description"),
            options=options,
            related_model=related_model,
            batch_size=batch_size,
            order=data.get("order", 0),
        )


class NonScoredQuestion(Question):
    def __init__(
        self,
        question: str,
        options: List[Option],
        allow_multiple: bool,
        related_model: QuestionRelatedModel,
        batch_size: int,
        description: Optional[str] = None,
        has_other: bool = False,
        has_none: bool = False,
        order: int = 0,
    ):
        super().__init__(question, "NON_SCORED", batch_size, description, order)
        self.options = options
        self.allow_multiple = allow_multiple
        self.has_other = has_other
        self.has_none = has_none
        self.related_model = related_model

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError("NON_SCORED question must have options")

        if not QuestionRelatedModel.is_member(self.related_model.value) and self.batch_size > 1:
            raise ValueError(
                f"NON_SCORED question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        response_category = QuestionResponseCategory.CHOICE_MULTI if self.allow_multiple else QuestionResponseCategory.CHOICE_ONE_NO_SCORE
        return TemplateQuestion(
            title=self.title,  # question is stored as 'title' in database
            description=self.description,
            response_category=response_category,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            related_model=self.related_model,
            has_other=self.has_other,
            has_none=self.has_none,
            options=[
                TemplateOption(value=opt.value, label_text=opt.label_text, order=i, reference_file=opt.reference_file)
                for i, opt in enumerate(self.options)
            ],
        )

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_QUESTION_KEY, Any], batch_size: int) -> "NonScoredQuestion":
        if "options" not in data or not data["options"]:
            raise ValueError("NON_SCORED question must have options")
        if "allow_multiple" not in data:
            raise ValueError("NON_SCORED question must specify allow_multiple")

        option_length = len(data["options"])
        if option_length < 1 or option_length > 9:
            raise ValueError("NON_SCORED question must have between 1 and 9 options")

        related_model = (
            QuestionRelatedModel.from_value(data.get("related_model", QuestionRelatedModel.ALL.value)) if batch_size > 1 else QuestionRelatedModel.ALL
        )
        options = [Option.from_dict(opt, value=None, order=i, is_score=False) for i, opt in enumerate(data["options"])]
        return cls(
            question=data["question"],
            description=data.get("description"),
            options=options,
            allow_multiple=data["allow_multiple"],
            related_model=related_model,
            batch_size=batch_size,
            has_other=data.get("has_other", False),
            has_none=data.get("has_none", False),
            order=data.get("order", 0),
        )


class ComparisonQuestion(Question):
    def __init__(
        self,
        question: str,
        meta_data: QuestionMetadataColumn,
        related_model: QuestionRelatedModel,
        batch_size: int,
        scale: int = 5,
        description: Optional[str] = None,
        order: int = 0,
    ):
        super().__init__(question, "COMPARISON", batch_size, description, order)
        self.scale = scale
        self.meta_data = meta_data
        self.related_model = related_model

    def validate(self) -> None:
        super().validate()
        if self.scale < 2 or self.scale > 9:
            raise ValueError("COMPARISON question scale must be between 2 and 9")

        if not QuestionRelatedModel.is_member(self.related_model.value) and self.batch_size > 1:
            raise ValueError(
                f"COMPARISON question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self.title,  # question is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.SCALE_LINEAR,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            scale=self.scale,
            meta_data=self.meta_data,
            related_model=self.related_model,
        )

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_QUESTION_KEY, Any], batch_size: int) -> "ComparisonQuestion":
        error_message = "COMPARISON question must have 'anchor_label' in the format: {'anchor_label': {'title': optional string, 'label_text': {'left': string, 'right': string}}}"
        if "anchor_label" not in data or "label_text" not in data["anchor_label"]:
            raise ValueError(error_message)

        label_text = data["anchor_label"]["label_text"]
        if "left" not in label_text or "right" not in label_text:
            raise ValueError(error_message)

        related_model = (
            QuestionRelatedModel.from_value(data.get("related_model", QuestionRelatedModel.ALL.value)) if batch_size > 1 else QuestionRelatedModel.ALL
        )
        return cls(
            question=data["question"],
            description=data.get("description"),
            related_model=related_model,
            batch_size=batch_size,
            scale=data.get("scale", 5),
            meta_data=QuestionMetadataColumn(
                linear_scale=QuestionMetadataLinearScale(
                    title=data.get("anchor_label", {}).get("title", None),
                    label_text=QuestionMetadataPosition(left=f"A {label_text['left']}", right=f"B {label_text['right']}"),
                )
            ),
            order=data.get("order", 0),
        )


class Instruction(Question):
    def __init__(
        self,
        instruction: str,
        category: InstructionCategory,
        batch_size: int,
        description: Optional[str] = None,
        order: int = 0,
        reference_file: Optional[str] = None,
    ):
        super().__init__(instruction, "INSTRUCTION", batch_size, description, order)
        self.category = category
        self.reference_file = reference_file

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.category, InstructionCategory):
            raise ValueError(
                f"Invalid instruction type: {self.category}: Use one of {', '.join([InstructionCategory.DO.value, InstructionCategory.WARNING.value, InstructionCategory.DONT.value])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        # Map GuideCategory to QuestionUsageType
        usage_type_map = {
            InstructionCategory.DO: QuestionUsageType.GUIDELINE_CORRECT,
            InstructionCategory.WARNING: QuestionUsageType.GUIDELINE_WARNING,
            InstructionCategory.DONT: QuestionUsageType.GUIDELINE_PROHIBIT,
        }

        return TemplateQuestion(
            title=self.title,  # instruction is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.INSTRUCTION,
            usage_type=usage_type_map[self.category],
            order=self.order,
            reference_file=self.reference_file,
            related_model=None,  # Instruction is not related to any model
        )

    @classmethod
    def from_dict(cls, data: Dict[TYPE_OF_QUESTION_KEY, Any], batch_size: int) -> "Instruction":
        try:
            category = InstructionCategory(data["type"])
        except ValueError:
            raise ValueError(
                f"Invalid instruction type: {data['type']}: Use one of {', '.join([InstructionCategory.DO.value, InstructionCategory.WARNING.value, InstructionCategory.DONT.value])}"
            )

        return cls(
            instruction=data["instruction"],
            description=data.get("description"),
            category=category,
            batch_size=batch_size,
            order=data.get("order", 0),
            reference_file=data.get("reference_file", None),
        )
