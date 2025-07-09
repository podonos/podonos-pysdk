import json as json_lib
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any, Tuple

from podonos.common.enum import Language
from podonos.core.base import *
from podonos.core.config import EvalConfigDefault
from podonos.core.types import TemplateQuestion
from podonos.core.query import NonScoredQuestion, Question, Instruction, ComparisonQuestion, ScoredQuestion


TYPE_OF_TEMPLATE_KEY = Literal["questions", "instructions"]


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
        required_keys = [
            "id",
            "code",
            "title",
            "description",
            "batch_size",
            "language",
            "created_time",
            "updated_time",
        ]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing {key} in {data}")

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


class TemplateJsonLoader:
    """Loader class for template JSON data"""

    @staticmethod
    def load_json(json: Optional[Dict] = None, json_file: Optional[str] = None) -> Dict[TYPE_OF_TEMPLATE_KEY, Any]:
        """Load template JSON data from a file"""
        # Validate input parameters
        if json is None and json_file is None:
            raise ValueError("Either 'json' or 'json_file' must be provided")
        if json is not None and json_file is not None:
            raise ValueError("Only one of 'json' or 'json_file' should be provided")

        # Get template data
        if json_file is not None:
            log.info(f"Reading template from file: {json_file}")
            json_path = Path(json_file)
            if not json_path.exists():
                raise FileNotFoundError(f"JSON file not found: {json_file}")

            with open(json_path, "r", encoding="utf-8") as f:
                template_data = json_lib.load(f)

        else:
            log.info("Using provided template JSON")
            assert json is not None
            template_data = json
        return template_data


class TemplateValidator:
    """Validator class for template JSON data"""

    @staticmethod
    def validate_and_create_questions(
        data: Dict[TYPE_OF_TEMPLATE_KEY, Any], batch_size: int
    ) -> Tuple[List[TemplateQuestion], List[TemplateQuestion]]:
        """Validates the template JSON data and returns TemplateQuestion objects.

        Args:
            data: Template JSON data
            batch_size: Number of stimuli to compare (1 for single, 2 for double, etc.)

        Returns:
            Tuple of (instructions, questions)

        Raises:
            ValueError: If template structure is invalid or contains incompatible questions
        """
        # Validate core questions (required)
        if "questions" not in data or not isinstance(data["questions"], list):
            raise ValueError("Template must contain a 'questions' list")

        question_length = len(data["questions"])
        if question_length < 1 or question_length > 9:
            raise ValueError("Template must contain between 1 and 9 questions")

        instructions = TemplateValidator.process_questions(data, "instructions", [Instruction], batch_size)
        core_questions = TemplateValidator.process_questions(data, "questions", [ScoredQuestion, NonScoredQuestion, ComparisonQuestion], batch_size)

        log.debug(f"Processed {len(instructions)} instructions and {len(core_questions)} questions")

        return instructions, core_questions

    @staticmethod
    def process_questions(data: dict, key: str, expected_types: List[type], batch_size: int) -> List[TemplateQuestion]:
        """
        Process questions from the given data dictionary.

        Args:
            data: The data dictionary containing questions.
            key: The key in the data dictionary to process.
            expected_types: The expected types of questions.
            order_start: The starting order number for questions.
            batch_size: The batch size for validation, if applicable.

        Returns:
            A list of processed TemplateQuestion objects.

        Raises:
            ValueError: If the questions are not in the expected format or type.
        """
        if key not in data or not data[key]:
            return []

        if not isinstance(data[key], list):
            raise ValueError(f"{key.capitalize()} must be in a list format")

        log.debug(f"Processing {len(data[key])} {key}...")
        questions = []
        for i, q_data in enumerate(data[key]):
            try:
                question = Question.from_dict(q_data, batch_size)
                question.validate()

                if not any(isinstance(question, expected_type) for expected_type in expected_types):
                    types = ", ".join([expected_type.__name__ for expected_type in expected_types])
                    raise ValueError(f"Question in {key} section must be one of the following types: {types}, got {q_data.get('type')}")

                if isinstance(question, ComparisonQuestion) and batch_size == 1:
                    raise ValueError(
                        "COMPARISON type questions are not allowed in single stimulus evaluation. "
                        "Please use batch_size=2 for comparison questions."
                    )

                if isinstance(question, Instruction) and question.reference_file:
                    TemplateValidator.check_if_reference_file_is_audio_file(question.reference_file)

                if (isinstance(question, ScoredQuestion) or isinstance(question, NonScoredQuestion)) and question.options:
                    for option in question.options:
                        if option.reference_file:
                            TemplateValidator.check_if_reference_file_is_audio_file(option.reference_file)

                template_question = question.to_template_question()
                template_question.order = i
                questions.append(template_question)
            except Exception as e:
                log.error(f"Failed to process {key} question {i}: {str(e)}")
                raise

        return questions

    @staticmethod
    def check_if_reference_file_is_audio_file(reference_file: Optional[str]) -> None:
        """Check if the reference file is valid"""
        if reference_file is None:
            return

        if not Path(reference_file).exists():
            raise ValueError(f"Reference file not found: {reference_file}")

        if not Path(reference_file).is_file():
            raise ValueError(f"Reference file is not a file: {reference_file}")

        if not Path(reference_file).suffix.lower() in [".wav", ".mp3", ".flac"]:
            raise ValueError(f"Reference file must be an audio file: {reference_file}. Supported formats: .wav, .mp3, .flac")
