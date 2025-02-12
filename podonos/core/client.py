import json as json_lib
from pathlib import Path
from typing import Any, Dict, Literal, Optional, List, Union
from requests import HTTPError

from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.base import *
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluation import Evaluation
from podonos.core.evaluator import Evaluator
from podonos.core.stimulus_stats import StimulusStats
from podonos.core.template import TemplateValidator
from podonos.service.template_service import TemplateService


class Client:
    """Podonos Client class. Used for creating individual evaluator and managing the evaluations."""

    _api_client: APIClient
    _initialized: bool = False

    def __init__(self, api_client: APIClient):
        self._api_client = api_client
        self._initialized = True

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
        use_power_normalization: bool = EvalConfigDefault.USE_POWER_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://docs.dyspatch.io/localization/supported_languages/

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. Default: NMOS
            lan: Human language for this audio. One of those in Language. Default: en-us
            granularity: Granularity of the evaluation scales. Either {1, 0.5}
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 10.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_power_normalization: Enable power normalization for evaluation.
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        if not EvalType.is_eval_type(type):
            raise ValueError(
                "Not supported evaluation types. Use one of the " "{'NMOS', 'QMOS', 'P808', 'SMOS', 'PREF', 'CUSTOM_SINGLE', 'CUSTOM_DOUBLE'}"
            )

        eval_config = EvalConfig(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            granularity=granularity,
            num_eval=num_eval,
            due_hours=due_hours,
            use_annotation=use_annotation,
            use_power_normalization=use_power_normalization,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )

        if EvalType.is_double(type):
            supported_types = EvalType.get_double_types()
        elif EvalType.is_single(type):
            supported_types = EvalType.get_single_types()
        else:
            raise ValueError(f"Invalid evaluation type: {type}")

        return Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)

    def create_evaluator_from_template(
        self,
        name: str,
        template_id: str,
        num_eval: int,
        desc: Optional[str] = None,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_power_normalization: bool = EvalConfigDefault.USE_POWER_NORMALIZATION,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """
        Creates a new evaluator using a predefined template.

        Args:
            name: This session name. Required.
            desc: Description of this session. Optional.
            template_id: The ID of the template to use for evaluation parameters.
            num_eval: The number of evaluators per file. Should be >=1.
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_power_normalization: Enable power normalization for evaluation.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If the template ID is invalid or not found.
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        if not template_id:
            raise ValueError("Template Id should exist")

        template_service = TemplateService(self._api_client)
        template = template_service.get_template_by_code(template_id)
        eval_config = EvalConfig(
            type=EvalType.CUSTOM_SINGLE.value if template.batch_size == 1 else EvalType.CUSTOM_DOUBLE.value,
            name=name,
            desc=desc,
            num_eval=num_eval,
            use_annotation=use_annotation,
            use_power_normalization=use_power_normalization,
            template_id=str(template.id),
            max_upload_workers=max_upload_workers,
        )

        if template.batch_size == 1:
            supported_types = EvalType.get_single_types()
        elif template.batch_size == 2:
            supported_types = EvalType.get_double_types()
        else:
            raise ValueError(f"Template has invalid type so please contact {PODONOS_CONTACT_EMAIL}")
        return Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)

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
        use_power_normalization: bool = EvalConfigDefault.USE_POWER_NORMALIZATION,
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
            use_power_normalization: Enable power normalization for evaluation. Default: False
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

        # Validate input parameters
        if json is None and json_file is None:
            raise ValueError("Either 'json' or 'json_file' must be provided")
        if json is not None and json_file is not None:
            raise ValueError("Only one of 'json' or 'json_file' should be provided")

        # Validate custom_type
        if custom_type not in ["SINGLE", "DOUBLE"]:
            raise ValueError('custom_type must be either "SINGLE" or "DOUBLE"')

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

        # Use the validator from template.py
        batch_size = 1 if custom_type == "SINGLE" else 2
        guide_questions, core_questions = TemplateValidator.validate_and_create_questions(template_data, batch_size)
        log.info("Template JSON is validated.")

        # Create an evaluator
        eval_type = EvalType.CUSTOM_SINGLE if custom_type == "SINGLE" else EvalType.CUSTOM_DOUBLE
        eval_config = EvalConfig(
            name=name,
            desc=desc,
            type=eval_type.value,
            lan=lan,
            num_eval=num_eval,
            use_annotation=use_annotation,
            use_power_normalization=use_power_normalization,
            max_upload_workers=max_upload_workers,
        )
        log.info(f"Created evaluation config with type: {eval_type.value}")

        if custom_type == "SINGLE":
            supported_types = EvalType.get_single_types()
        elif custom_type == "DOUBLE":
            supported_types = EvalType.get_double_types()
        else:
            raise ValueError('custom_type must be either "SINGLE" or "DOUBLE"')

        template_service = TemplateService(self._api_client)
        evaluator = Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)
        try:
            if guide_questions:
                log.debug(f"Creating {len(guide_questions)} guide questions...")
                response = template_service.create_template_questions_by_evaluation_id_and_questions(evaluator.get_evaluation_id(), guide_questions)

                for q_response, question in zip(response, guide_questions):
                    question.id = q_response["id"]

            if core_questions:
                log.debug(f"Creating {len(core_questions)} core questions...")
                response = template_service.create_template_questions_by_evaluation_id_and_questions(evaluator.get_evaluation_id(), core_questions)

                for q_response, question in zip(response, core_questions):
                    question.id = q_response["id"]

            # Create options for questions that have options
            questions_with_options = [q for q in (guide_questions + core_questions) if q.options]
            if questions_with_options:
                log.debug(f"Creating options for {len(questions_with_options)} questions...")
                for question in questions_with_options:
                    if question.id:
                        template_service.create_template_options_by_question_id_and_options(question.id, question.options)

        except Exception as e:
            log.error(f"Failed to create template: {str(e)}")
            raise HTTPError(f"Failed to create template questions: {e}")

        log.info("Template creation completed successfully")
        return evaluator

    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Args: None

        Returns:
            Evaluation containing all the evaluation info
        """
        log.check(self._api_client)
        try:
            response = self._api_client.get("evaluations")
            response.raise_for_status()
            evaluations = [Evaluation.from_dict(evaluation) for evaluation in response.json()]
            return [evaluation.to_dict() for evaluation in evaluations]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation list: {e}")

    def get_stats_dict_by_id(self, evaluation_id: str) -> List[Dict[str, Any]]:
        """Gets a list of evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.

        Returns:
            List of statistics for the evaluation.
        """
        log.check(self._api_client)
        try:
            response = self._api_client.get(f"evaluations/{evaluation_id}/stats")
            if response.status_code == 400:
                log.info(f"Bad Request: The {evaluation_id} is an invalid evaluation id")
                return []

            response.raise_for_status()
            stats = [StimulusStats.from_dict(stats) for stats in response.json()]
            return [stat.to_dict() for stat in stats]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation stats: {e}")

    def download_stats_csv_by_id(self, evaluation_id: str, output_path: str) -> None:
        """Downloads the evaluation statistics into CSV referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            output_path: Path to the output CSV.

        Returns: None
        """
        log.check_ne(evaluation_id, "")
        log.check_ne(output_path, "")
        stats = self.get_stats_dict_by_id(evaluation_id)

        with open(output_path, "w") as f:
            question_headers = ["question_title", "question_order"]
            file_headers = ["name", "model_tag", "tags", "type"]
            stat_fields = ["mean", "median", "std", "sem", "ci_95"]

            option_keys = set()
            for stat in stats:
                if "options" in stat:
                    option_keys.update(stat["options"].keys())

            all_headers = question_headers + file_headers + stat_fields + sorted(list(option_keys))
            f.write(",".join(all_headers) + "\n")

            for stat in stats:
                question = stat.get("question", {})
                for file in stat["files"]:
                    row_data = [
                        question.get("title", ""),
                        str(question.get("order", "")),
                        file["name"],
                        file["model_tag"],
                        ";".join(file["tags"]),
                        file["type"],
                    ]

                    for field in stat_fields:
                        row_data.append(str(stat.get(field, "")))

                    options = stat.get("options", {})
                    for key in sorted(list(option_keys)):
                        row_data.append(str(options.get(key, "")))

                    f.write(",".join(row_data) + "\n")
