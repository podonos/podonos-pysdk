from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

from podonos.common.enum import Language
from podonos.core.base import *
from podonos.core.types import TemplateQuestion
from podonos.core.query import Question, GuideQuestion, ComparisonQuestion


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


class TemplateValidator:
    """Validator class for template JSON data"""

    @staticmethod
    def validate_and_create_questions(data: Dict[str, Any], batch_size: int) -> Tuple[List[TemplateQuestion], List[TemplateQuestion]]:
        """Validates the template JSON data and returns TemplateQuestion objects.

        Args:
            data: Template JSON data
            batch_size: Number of stimuli to compare (1 for single, 2 for double, etc.)

        Returns:
            Tuple of (guide_template_questions, core_template_questions)

        Raises:
            ValueError: If template structure is invalid or contains incompatible questions
        """
        # Validate core questions (required)
        if "query" not in data or not isinstance(data["query"], list):
            raise ValueError("Template must contain a 'query' list")

        if not data["query"]:
            raise ValueError("Template must contain at least one query question")

        guide_questions = []
        core_questions = []
        guide_order = 0
        core_order = 0

        # Process guide questions if exist
        if "guide" in data and data["guide"]:
            if not isinstance(data["guide"], list):
                raise ValueError("Guide questions must be in a list format")

            log.debug(f"Processing {len(data['guide'])} guide questions...")
            for i, q_data in enumerate(data["guide"]):
                try:
                    question = Question.from_dict(q_data)
                    question.validate()

                    if not isinstance(question, GuideQuestion):
                        raise ValueError(f"Question in guide section must be of type GUIDE, got {q_data.get('type')}")

                    template_question = question.to_template_question()
                    template_question.order = guide_order
                    guide_order += 1
                    guide_questions.append(template_question)
                except Exception as e:
                    log.error(f"Failed to process guide question {i}: {str(e)}")
                    raise

        # Process core questions
        log.debug(f"Processing {len(data['query'])} core questions...")
        for i, q_data in enumerate(data["query"]):
            try:
                question = Question.from_dict(q_data)
                question.validate()

                if batch_size == 1 and isinstance(question, ComparisonQuestion):
                    raise ValueError(
                        "COMPARISON type questions are not allowed in single stimulus evaluation. "
                        "Please use batch_size=2 for comparison questions."
                    )

                if isinstance(question, GuideQuestion):
                    raise ValueError(f"GUIDE type questions are not allowed in query section")

                template_question = question.to_template_question()
                template_question.order = core_order
                core_order += 1
                core_questions.append(template_question)

            except Exception as e:
                log.error(f"Failed to process core question {i} ({q_data.get('type', 'unknown type')}): {str(e)}")
                raise

        log.debug(f"Processed {len(guide_questions)} guide questions and {len(core_questions)} core questions")

        return guide_questions, core_questions
