from typing import Any, Dict, Literal, Optional, List, Union

from podonos.core.api import APIClient
from podonos.core.base import *
from podonos.core.config import EvalConfigDefault
from podonos.core.evaluator import Evaluator
from podonos.core.template import Template
from podonos.evaluation import AIEvaluation, HumanEvaluation
from podonos.service import CollectionService, EvaluationService, ScriptService, TemplateService


class Client:
    """Podonos Client class. Used for creating individual evaluator and managing the evaluations."""

    _api_client: APIClient
    _initialized: bool = False

    # Services
    _collection_service: CollectionService
    _evaluation_service: EvaluationService
    _script_service: ScriptService
    _template_service: TemplateService

    # Evaluators
    _ai_evaluation: AIEvaluation
    _human_evaluation: HumanEvaluation

    def __init__(self, api_client: APIClient):
        self._api_client = api_client
        self._initialized = True
        self._collection_service = CollectionService(self._api_client)
        self._evaluation_service = EvaluationService(self._api_client)
        self._script_service = ScriptService(self._api_client)
        self._template_service = TemplateService(self._api_client)

        self._ai_evaluation = AIEvaluation(self._api_client)
        self._human_evaluation = HumanEvaluation(self._api_client, self._evaluation_service, self._template_service)

    def create_evaluator(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalConfigDefault.TYPE.value,
        lan: str = EvalConfigDefault.LAN.value,
        granularity: float = EvalConfigDefault.GRANULARITY,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://www.podonos.com/docs/reference#param-lan

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. Default: NMOS
            lan: Human language for this audio. One of those in Language. Default: en-us
            granularity: Granularity of the evaluation scales. Either {1, 0.5}
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 10.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.
            use_annotation: Enable detailed annotation on script for detailed comments.
            use_loudness_normalization: Enable loudness normalization for evaluation.
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")
        return self._human_evaluation.create(
            name,
            desc,
            type,
            lan,
            granularity,
            num_eval,
            due_hours,
            use_annotation,
            use_loudness_normalization,
            auto_start,
            max_upload_workers,
        )

    def create_evaluator_from_template(
        self,
        name: str,
        template_id: str,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        desc: Optional[str] = None,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
    ) -> Evaluator:
        """
        Creates a new evaluator using a predefined template.

        Args:
            name: This session name. Required.
            desc: Description of this session. Optional.
            template_id: The ID of the template to use for evaluation parameters.
            num_eval: The number of evaluators per file. Should be >= 1. Default: 10
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            use_annotation: Enable detailed annotation on script for detailed comments. Default: False
            use_loudness_normalization: Enable loudness normalization for evaluation. Default: True

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If the template ID is invalid or not found.
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        return self._human_evaluation.create_from_template(
            name, template_id, num_eval, desc, use_annotation, use_loudness_normalization, auto_start, max_upload_workers
        )

    def create_evaluator_from_template_json(
        self,
        json: Optional[Dict] = None,
        json_file: Optional[str] = None,
        name: Optional[str] = None,
        custom_type: Union[Literal["SINGLE"], Literal["DOUBLE"]] = "SINGLE",
        desc: Optional[str] = None,
        lan: str = EvalConfigDefault.LAN.value,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """Creates a new evaluator using a template JSON.

        Args:
            json: Template JSON as a dictionary. Optional if json_file is provided.
            json_file: Path to the JSON template file. Optional if json is provided.
            name: This evaluation name. Required.
            custom_type: Type of evaluation ("SINGLE" or "DOUBLE")
            desc: Description of this evaluation. Optional.
            lan: Language for evaluation. Defaults to EvalConfigDefault.LAN.value.
            num_eval: The number of evaluators per file. Should be >=1.
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_loudness_normalization: Enable loudness normalization for evaluation. Default: False
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If neither json nor json_file is provided, or if both are provided
            ValueError: If custom_type is not "SINGLE" or "DOUBLE"
            ValueError: If the JSON is invalid or contains incompatible question types
            FileNotFoundError: If the json_file path doesn't exist
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        return self._human_evaluation.create_from_template_json(
            json, json_file, name, custom_type, desc, lan, num_eval, use_annotation, use_loudness_normalization, auto_start, max_upload_workers
        )

    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Args: None

        Returns:
            Evaluation containing all the evaluation info
        """
        return self._evaluation_service.get_evaluation_list()

    def get_stats_json_by_id(self, evaluation_id: str, group_by: Literal["question", "script", "model"] = "question") -> List[Dict[str, Any]]:
        """Gets a list of evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            group_by: Group by question or script. Default: "question".
                      "script" and "model" are only available for single-question evaluation.

        Returns:
            List of statistics for the evaluation.
        """
        return self._evaluation_service.get_stats_json_by_id(evaluation_id, group_by)

    def download_evaluation_files_by_evaluation_id(self, evaluation_id: str, output_dir: str) -> str:
        """Download evaluation files"""
        return self._evaluation_service.download_evaluation_files_by_evaluation_id(evaluation_id, output_dir)

    def get_eval_template_info(self, template_id: str) -> Dict[str, Any]:
        """Gets detailed information on the evaluation template by id.

        Args:
            template_id: Evaluation template ID.

        Returns:
            JSON containing the evaluation template info.

        Raises:


        """
        try:
            template = self._template_service.get_template_by_code(template_id)
        except:
            raise ValueError(f"Cannot find the template. Please check the id {template_id}.")
        json = {
            "id": template.id,
            "code": template.code,
            "title": template.title,
            "description": template.description,
            "language": template.language,
            "created_time": template.created_time,
            "updated_time": template.updated_time,
        }
        if template.batch_size == 1:
            json["eval_type"] = "Single"
        elif template.batch_size == 2:
            json["eval_type"] = "Double"
        elif template.batch_size == 3:
            json["eval_type"] = "Triple"
        else:
            ValueError(f"Unknown eval type (batch_size): {template.batch_size}.")

        return json
