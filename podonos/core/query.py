import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from typing_extensions import Self

from podonos.common.enum import (
    InstructionCategory,
    QuestionRelatedModel,
    QuestionResponseCategory,
    QuestionType,
    QuestionUsageType,
)
from podonos.common.validator import Rules, validate_args
from podonos.core.types import (
    QuestionMetadataColumn,
    QuestionMetadataLinearScale,
    QuestionMetadataPosition,
    TemplateOption,
    TemplateQuestion,
)

TYPE_OF_OPTION_KEY = Literal["score", "label_text", "reference_file", "is_annotation_required"]
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
    "reference_files",
    "anchor_label",
]
TYPE_OF_REFERENCE_FILES = Optional[List[Dict[Literal["path", "type"], str]]]


@dataclass
class Option:
    value: str
    label_text: Optional[str] = None
    order: int = 0
    reference_file: Optional[str] = None
    is_annotation_required: bool = False

    @classmethod
    def from_dict(
        cls,
        data: Dict[TYPE_OF_OPTION_KEY, Any],
        value: Optional[str] = None,
        order: int = 0,
        is_score: bool = True,
    ) -> Self:
        if not data.get("label_text"):
            raise ValueError("Option must have a non-empty 'label_text' field")
        if not is_score:
            return cls(
                value=data["label_text"],
                order=order,
                reference_file=data.get("reference_file", None),
                is_annotation_required=bool(data.get("is_annotation_required", False)),
            )
        if not value:
            raise ValueError("Score question's option must have a value")
        return cls(
            value=value,
            label_text=data.get("label_text"),
            order=order,
            reference_file=data.get("reference_file", None),
            is_annotation_required=bool(data.get("is_annotation_required", False)),
        )


class Question(ABC):
    def __init__(
        self,
        question_or_instruction: str,
        type: str,
        batch_size: int,
        description: Optional[str] = None,
        order: int = 0,
        *,
        title: Optional[str] = None,  # Deprecated: use question_or_instruction instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'question_or_instruction' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            if question_or_instruction:
                # Both provided - prefer question_or_instruction but warn
                pass
            else:
                question_or_instruction = title

        self._question_or_instruction = question_or_instruction
        self.type = type
        self.batch_size = batch_size
        self.description = description
        self.order = order

    @property
    def question_or_instruction(self) -> str:
        """The question or instruction text."""
        return self._question_or_instruction

    @property
    def title(self) -> str:
        """Deprecated: Use question_or_instruction instead."""
        warnings.warn(
            "The 'title' property is deprecated. Use 'question_or_instruction' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._question_or_instruction

    @abstractmethod
    def validate(self) -> None:
        """Validate the question details."""
        if not self._question_or_instruction:
            raise ValueError("Question must have a 'question' or 'instruction'")

    @abstractmethod
    def to_template_question(self) -> TemplateQuestion:
        """Convert to TemplateQuestion."""
        pass

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        """Create appropriate Question instance from dictionary."""
        question_type_str = data.get("type")
        if not question_type_str:
            raise ValueError("Question must have a type")

        # Check if it's an InstructionCategory (DO, WARNING, DONT, EXAMPLE)
        is_instruction = False
        try:
            InstructionCategory(question_type_str)
            is_instruction = True
        except ValueError:
            pass

        # Validate question type if not an instruction
        if not is_instruction:
            try:
                QuestionType(question_type_str)
            except ValueError:
                valid_types = [t.value for t in QuestionType] + [
                    t.value for t in InstructionCategory
                ]
                raise ValueError(
                    f"Unknown question type: {question_type_str} (must be one of {', '.join(valid_types)})"
                )

        # In ranking mode, allow only Instruction (DO, WARNING, DONT, EXAMPLE) and COMPARISON
        if allow_ranking_only:
            allowed_types = {QuestionType.COMPARISON.value} | {
                t.value for t in InstructionCategory
            }
            if question_type_str not in allowed_types:
                raise ValueError(
                    "RANKING evaluation allows only Instruction (DO/WARNING/DONT/EXAMPLE) and COMPARISON question types"
                )

        question_map = {
            QuestionType.SCORED.value: ScoredQuestion,
            QuestionType.NON_SCORED.value: NonScoredQuestion,
            QuestionType.COMPARISON.value: ComparisonQuestion,
            QuestionType.ANNOTATION.value: AnnotationQuestion,
            InstructionCategory.DO.value: Instruction,
            InstructionCategory.WARNING.value: Instruction,
            InstructionCategory.DONT.value: Instruction,
            InstructionCategory.EXAMPLE.value: Instruction,
        }

        return question_map[question_type_str].from_dict(data, batch_size)


class ScoredQuestion(Question):
    def __init__(
        self,
        question: str = "",
        options: Optional[List[Option]] = None,
        related_model: Optional[QuestionRelatedModel] = None,
        batch_size: int = 1,
        description: Optional[str] = None,
        order: int = 0,
        *,
        title: Optional[str] = None,  # Deprecated: use question instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'question' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if not question:
                question = title

        super().__init__(
            question_or_instruction=question,
            type=QuestionType.SCORED.value,
            batch_size=batch_size,
            description=description,
            order=order,
        )
        self.options = options if options is not None else []
        self.related_model = (
            related_model if related_model is not None else QuestionRelatedModel.ALL
        )

    @property
    def question(self) -> str:
        """The question text."""
        return self._question_or_instruction

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError(f"{QuestionType.SCORED.value} question must have options")

        if (
            not QuestionRelatedModel.is_member(self.related_model.value)
            and self.batch_size > 1
        ):
            raise ValueError(
                f"{QuestionType.SCORED.value} question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

        # Validate that all option values are numbers
        for option in self.options:
            try:
                float(option.value)
            except ValueError:
                raise ValueError(
                    f"{QuestionType.SCORED.value} question option value '{option.value}' must be a number"
                )

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self._question_or_instruction,  # question is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.CHOICE_ONE,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            related_model=self.related_model,
            options=[
                TemplateOption(
                    value=opt.value,
                    label_text=opt.label_text,
                    order=i,
                    reference_file=opt.reference_file,
                    is_annotation_required=opt.is_annotation_required,
                )
                for i, opt in enumerate(self.options)
            ],
        )

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        if "options" not in data or not data["options"]:
            raise ValueError(f"{QuestionType.SCORED.value} question must have options")

        option_length = len(data["options"])
        if option_length < 1 or option_length > 9:
            raise ValueError(
                f"{QuestionType.SCORED.value} question must have between 1 and 9 options"
            )

        related_model = (
            QuestionRelatedModel.from_value(
                data.get("related_model", QuestionRelatedModel.ALL.value)
            )
            if batch_size > 1
            else QuestionRelatedModel.ALL
        )
        option_values = [str(score) for score in range(option_length, 0, -1)]
        options = [
            Option.from_dict(opt, value=option_values[i], order=i, is_score=True)
            for i, opt in enumerate(data["options"])
        ]
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
        question: str = "",
        options: Optional[List[Option]] = None,
        allow_multiple: bool = False,
        related_model: Optional[QuestionRelatedModel] = None,
        batch_size: int = 1,
        description: Optional[str] = None,
        has_other: bool = False,
        has_none: bool = False,
        order: int = 0,
        *,
        title: Optional[str] = None,  # Deprecated: use question instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'question' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if not question:
                question = title

        super().__init__(
            question_or_instruction=question,
            type=QuestionType.NON_SCORED.value,
            batch_size=batch_size,
            description=description,
            order=order,
        )
        self.options = options if options is not None else []
        self.allow_multiple = allow_multiple
        self.has_other = has_other
        self.has_none = has_none
        self.related_model = (
            related_model if related_model is not None else QuestionRelatedModel.ALL
        )

    @property
    def question(self) -> str:
        """The question text."""
        return self._question_or_instruction

    def validate(self) -> None:
        super().validate()
        if not self.options:
            raise ValueError(
                f"{QuestionType.NON_SCORED.value} question must have options"
            )

        if (
            not QuestionRelatedModel.is_member(self.related_model.value)
            and self.batch_size > 1
        ):
            raise ValueError(
                f"{QuestionType.NON_SCORED.value} question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        response_category = (
            QuestionResponseCategory.CHOICE_MULTI
            if self.allow_multiple
            else QuestionResponseCategory.CHOICE_ONE_NO_SCORE
        )
        return TemplateQuestion(
            title=self._question_or_instruction,  # question is stored as 'title' in database
            description=self.description,
            response_category=response_category,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            related_model=self.related_model,
            has_other=self.has_other,
            has_none=self.has_none,
            options=[
                TemplateOption(
                    value=opt.value,
                    label_text=opt.label_text,
                    order=i,
                    reference_file=opt.reference_file,
                    is_annotation_required=opt.is_annotation_required,
                )
                for i, opt in enumerate(self.options)
            ],
        )

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        if "options" not in data or not data["options"]:
            raise ValueError(
                f"{QuestionType.NON_SCORED.value} question must have options"
            )
        if "allow_multiple" not in data:
            raise ValueError(
                f"{QuestionType.NON_SCORED.value} question must specify allow_multiple"
            )

        option_length = len(data["options"])
        if option_length < 1 or option_length > 9:
            raise ValueError(
                f"{QuestionType.NON_SCORED.value} question must have between 1 and 9 options"
            )

        related_model = (
            QuestionRelatedModel.from_value(
                data.get("related_model", QuestionRelatedModel.ALL.value)
            )
            if batch_size > 1
            else QuestionRelatedModel.ALL
        )
        options = [
            Option.from_dict(opt, value=None, order=i, is_score=False)
            for i, opt in enumerate(data["options"])
        ]
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
        question: str = "",
        meta_data: Optional[QuestionMetadataColumn] = None,
        related_model: Optional[QuestionRelatedModel] = None,
        batch_size: int = 1,
        scale: int = 5,
        description: Optional[str] = None,
        order: int = 0,
        *,
        title: Optional[str] = None,  # Deprecated: use question instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'question' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if not question:
                question = title

        super().__init__(
            question_or_instruction=question,
            type=QuestionType.COMPARISON.value,
            batch_size=batch_size,
            description=description,
            order=order,
        )
        self.scale = scale
        self.meta_data = meta_data
        self.related_model = (
            related_model if related_model is not None else QuestionRelatedModel.ALL
        )

    @property
    def question(self) -> str:
        """The question text."""
        return self._question_or_instruction

    def validate(self) -> None:
        super().validate()
        if self.scale < 2 or self.scale > 9:
            raise ValueError(
                f"{QuestionType.COMPARISON.value} question scale must be between 2 and 9"
            )

        if (
            not QuestionRelatedModel.is_member(self.related_model.value)
            and self.batch_size > 1
        ):
            raise ValueError(
                f"{QuestionType.COMPARISON.value} question must have one of the following valid related_models: {', '.join([item.value for item in QuestionRelatedModel])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        return TemplateQuestion(
            title=self._question_or_instruction,  # question is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.SCALE_LINEAR,
            usage_type=QuestionUsageType.SCORE,
            order=self.order,
            scale=self.scale,
            meta_data=self.meta_data,
            related_model=self.related_model,
        )

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        error_message = f"{QuestionType.COMPARISON.value} question must have 'anchor_label' in the format: {{'anchor_label': {{'title': optional string, 'label_text': {{'left': string, 'right': string}}}}}}"
        if "anchor_label" not in data or "label_text" not in data["anchor_label"]:
            raise ValueError(error_message)

        label_text = data["anchor_label"]["label_text"]
        if "left" not in label_text or "right" not in label_text:
            raise ValueError(error_message)

        related_model = (
            QuestionRelatedModel.from_value(
                data.get("related_model", QuestionRelatedModel.ALL.value)
            )
            if batch_size > 1
            else QuestionRelatedModel.ALL
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
                    label_text=QuestionMetadataPosition(
                        left=f"A {label_text['left']}", right=f"B {label_text['right']}"
                    ),
                )
            ),
            order=data.get("order", 0),
        )


class Instruction(Question):
    def __init__(
        self,
        instruction: str = "",
        category: Optional[InstructionCategory] = None,
        batch_size: int = 1,
        description: Optional[str] = None,
        order: int = 0,
        reference_files: TYPE_OF_REFERENCE_FILES = None,
        *,
        title: Optional[str] = None,  # Deprecated: use instruction instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'instruction' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if not instruction:
                instruction = title

        super().__init__(
            question_or_instruction=instruction,
            type=QuestionType.INSTRUCTION.value,
            batch_size=batch_size,
            description=description,
            order=order,
        )
        self.category = category if category is not None else InstructionCategory.DO
        self.reference_files = reference_files

    @property
    def instruction(self) -> str:
        """The instruction text."""
        return self._question_or_instruction

    def validate(self) -> None:
        super().validate()
        if not isinstance(self.category, InstructionCategory):  # type: ignore
            raise ValueError(
                f"Invalid instruction type: {self.category}: Use one of {', '.join([InstructionCategory.DO.value, InstructionCategory.WARNING.value, InstructionCategory.DONT.value])}"
            )

    def to_template_question(self) -> TemplateQuestion:
        # Map GuideCategory to QuestionUsageType
        usage_type_map: Dict[InstructionCategory, QuestionUsageType] = {
            InstructionCategory.DO: QuestionUsageType.GUIDELINE_CORRECT,
            InstructionCategory.WARNING: QuestionUsageType.GUIDELINE_WARNING,
            InstructionCategory.DONT: QuestionUsageType.GUIDELINE_PROHIBIT,
            InstructionCategory.EXAMPLE: QuestionUsageType.GUIDELINE_EXAMPLE,
        }

        return TemplateQuestion(
            title=self._question_or_instruction,  # instruction is stored as 'title' in database
            description=self.description,
            response_category=QuestionResponseCategory.INSTRUCTION,
            usage_type=usage_type_map[self.category],
            order=self.order,
            reference_files=self.reference_files,
            related_model=None,  # Instruction is not related to any model
        )

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        try:
            category = InstructionCategory(data["type"])
        except ValueError:
            raise ValueError(
                f"Invalid instruction type: {data['type']}: Use one of {', '.join([InstructionCategory.DO.value, InstructionCategory.WARNING.value, InstructionCategory.DONT.value])}"
            )

        if "reference_file" in data:
            raise ValueError(
                "The 'reference_file' field is not allowed for instruction questions. Please use 'reference_files' instead."
            )

        if "reference_files" in data and not isinstance(data["reference_files"], list):
            raise ValueError("Reference files must be a List")

        for reference_file in data.get("reference_files", []):
            if not isinstance(reference_file, Dict):
                raise ValueError("Reference files must be a List of Dict")
            if "path" not in reference_file or "type" not in reference_file:
                raise ValueError("Reference files must have 'path' and 'type' fields")
            if reference_file["type"] not in ["reference", "target", "audio"]:
                raise ValueError(
                    "Reference file type must be one of the following: reference, target, audio"
                )

        if len(data.get("reference_files", [])) > 3:
            raise ValueError("Instruction questions can have at most 3 reference files")

        return cls(
            instruction=data["instruction"],
            description=data.get("description"),
            category=category,
            batch_size=batch_size,
            order=data.get("order", 0),
            reference_files=data.get("reference_files", None),
        )


class AnnotationQuestion(Question):
    """
    Question type for collecting free-text annotations from evaluators.

    Annotations allow evaluators to provide detailed feedback about audio files.
    The related_model parameter controls which audio(s) the annotation applies to:
    - For single-stimulus evaluations (batch_size=1): must be ALL or None
    - For double/triple evaluations (batch_size>=2): must be MODEL_A or MODEL_B

    Args:
        question: The annotation prompt/question text shown to evaluators
        batch_size: The evaluation's batch_size (1=single, 2=double, 3=triple)
        related_model: Which audio the annotation applies to (ALL, MODEL_A, MODEL_B)
        description: Optional additional description
        order: Display order (default 0)
        title: Deprecated. Use question instead.

    Raises:
        ValueError: If question is empty/whitespace or related_model is invalid for batch_size
    """

    def __init__(
        self,
        question: str = "",
        batch_size: int = 1,
        related_model: Optional[QuestionRelatedModel] = None,
        description: Optional[str] = None,
        order: int = 0,
        *,
        title: Optional[str] = None,  # Deprecated: use question instead
    ):
        # Handle deprecated 'title' parameter
        if title is not None:
            warnings.warn(
                "The 'title' parameter is deprecated. Use 'question' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            if not question:
                question = title

        super().__init__(
            question_or_instruction=question,
            type=QuestionType.ANNOTATION.value,
            batch_size=batch_size,
            description=description,
            order=order,
        )
        self.related_model = related_model

    @property
    def question(self) -> str:
        """The question text."""
        return self._question_or_instruction

    def validate(self) -> None:
        """Validate annotation question configuration."""
        super().validate()
        # Validate question is not empty or whitespace
        if (
            not self._question_or_instruction
            or not self._question_or_instruction.strip()
        ):
            raise ValueError(
                "AnnotationQuestion question cannot be empty or whitespace"
            )

        if self.batch_size == 1:
            # Single-stimulus: related_model must be ALL or None
            if (
                self.related_model is not None
                and self.related_model != QuestionRelatedModel.ALL
            ):
                raise ValueError(
                    f"AnnotationQuestion related_model must be ALL for single-stimulus evaluations "
                    f"(batch_size=1), got {self.related_model.value}"
                )
        else:
            # Double/Triple (batch_size >= 2): related_model must be MODEL_A or MODEL_B
            if self.related_model is None:
                raise ValueError(
                    f"AnnotationQuestion related_model is required for multi-stimulus evaluations "
                    f"(batch_size={self.batch_size}). Must be MODEL_A or MODEL_B."
                )
            if self.related_model == QuestionRelatedModel.ALL:
                raise ValueError(
                    f"AnnotationQuestion related_model cannot be ALL for multi-stimulus evaluations "
                    f"(batch_size={self.batch_size}). Must be MODEL_A or MODEL_B."
                )

    def to_template_question(self) -> TemplateQuestion:
        """Convert to TemplateQuestion for API submission."""
        # Determine related_model value (default to ALL for single-stimulus)
        related_model = self.related_model
        if related_model is None and self.batch_size == 1:
            related_model = QuestionRelatedModel.ALL

        return TemplateQuestion(
            title=self._question_or_instruction,
            response_category=QuestionResponseCategory.ANNOTATION,
            usage_type=QuestionUsageType.ANNOTATION,
            description=self.description,
            order=self.order,
            related_model=related_model,
        )

    @classmethod
    @validate_args(data=Rules.dict_not_none, batch_size=Rules.positive_not_none)
    def from_dict(
        cls,
        data: Dict[TYPE_OF_QUESTION_KEY, Any],
        batch_size: int,
        allow_ranking_only: bool = False,
    ) -> Self:
        """Create AnnotationQuestion from dictionary (JSON parsing)."""
        question_text = data.get("question", "")
        description = data.get("description")
        order = data.get("order", 0)

        # Parse related_model
        related_model_str = data.get("related_model")
        related_model = None
        if related_model_str:
            try:
                related_model = QuestionRelatedModel(related_model_str)
            except ValueError:
                raise ValueError(
                    f"Invalid related_model '{related_model_str}'. "
                    f"Must be one of: ALL, MODEL_A, MODEL_B"
                )

        return cls(
            question=question_text,
            batch_size=batch_size,
            related_model=related_model,
            description=description,
            order=order,
        )
