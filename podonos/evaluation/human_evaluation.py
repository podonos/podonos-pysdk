from typing import Dict, Literal, Optional, Union

from requests import HTTPError

from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluator import Evaluator
from podonos.core.template import TemplateJsonLoader, TemplateValidator
from podonos.service import EvaluationService, TemplateService


class HumanEvaluation:
    _api_client: APIClient
    _evaluation_service: EvaluationService
    _template_service: TemplateService

    def __init__(self, api_client: APIClient, evaluation_service: EvaluationService, template_service: TemplateService):
        self._api_client = api_client
        self._evaluation_service = evaluation_service
        self._template_service = template_service

    def create(
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
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_loudness_normalization: Enable loudness normalization for evaluation.
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this type is not supported.
        """

        if not EvalType.is_eval_type(type):
            raise ValueError(
                "Not supported evaluation types. Use one of the " "{'NMOS', 'QMOS', 'P808', 'CMOS', 'SMOS', 'PREF', 'CUSTOM_SINGLE', 'CUSTOM_DOUBLE'}"
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
            use_loudness_normalization=use_loudness_normalization,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )

        if EvalType.is_double(type):
            supported_types = EvalType.get_double_types()
        elif EvalType.is_single(type):
            supported_types = EvalType.get_single_types()
        elif EvalType.is_triple(type):
            supported_types = EvalType.get_triple_types()
        else:
            raise ValueError(f"Invalid evaluation type: {type}")

        return Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)

    def create_from_template(
        self,
        name: str,
        template_id: str,
        num_eval: int,
        desc: Optional[str] = None,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """
        Creates a new evaluator using a predefined template.

        Args:
            name: This session name. Required.
            desc: Description of this session. Optional.
            template_id: The ID of the template to use for evaluation parameters.
            num_eval: The number of evaluators per file. Should be >= 1.
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If the template ID is invalid or not found.
        """
        if not template_id:
            raise ValueError("Template Id should exist")

        template = self._template_service.get_template_by_code(template_id)
        if template.batch_size is None:
            raise ValueError(f"Template with id {template_id} has no batch size")

        eval_config = EvalConfig(
            type=EvalType.get_type_by_batch_size(template.batch_size).value,
            name=name,
            desc=desc,
            num_eval=num_eval,
            use_annotation=use_annotation,
            use_loudness_normalization=use_loudness_normalization,
            auto_start=auto_start,
            template_id=str(template.id),
            max_upload_workers=max_upload_workers,
        )

        if template.batch_size == 1:
            supported_types = EvalType.get_single_types()
        elif template.batch_size == 2:
            # CMOS isn't supported in create_from_template
            supported_types = [EvalType.SMOS, EvalType.PREF, EvalType.CUSTOM_DOUBLE]
        elif template.batch_size == 3:
            supported_types = EvalType.get_triple_types()
        else:
            raise ValueError(f"Template has invalid type so please contact {PODONOS_CONTACT_EMAIL}")
        return Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)

    def create_from_template_json(
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
        # Validate custom_type
        if custom_type not in ["SINGLE", "DOUBLE"]:
            raise ValueError('custom_type must be either "SINGLE" or "DOUBLE"')

        eval_type = EvalType.CUSTOM_SINGLE if custom_type == "SINGLE" else EvalType.CUSTOM_DOUBLE
        batch_size = 1 if custom_type == "SINGLE" else 2
        # Load template data
        template_data = TemplateJsonLoader.load_json(json, json_file)

        # Use the validator from template.py
        instructions, core_questions = TemplateValidator.validate_and_create_questions(template_data, batch_size)
        log.info("Template JSON is validated.")

        # Create an evaluator
        eval_config = EvalConfig(
            name=name,
            desc=desc,
            type=eval_type.value,
            lan=lan,
            num_eval=num_eval,
            use_annotation=use_annotation,
            use_loudness_normalization=use_loudness_normalization,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )
        log.info(f"Created evaluation config with type: {eval_type.value}")

        if custom_type == "SINGLE":
            supported_types = EvalType.get_single_types()
        elif custom_type == "DOUBLE":
            # CMOS isn't supported in create_from_template_json
            supported_types = [EvalType.SMOS, EvalType.PREF, EvalType.CUSTOM_DOUBLE]
        else:
            raise ValueError('custom_type must be either "SINGLE" or "DOUBLE"')

        template_service = TemplateService(self._api_client)
        evaluator = Evaluator(api_client=self._api_client, eval_config=eval_config, supported_eval_types=supported_types)
        try:
            if instructions:
                log.debug(f"Creating {len(instructions)} instructions...")
                instructions = template_service.create_template_questions_by_evaluation_id_and_questions(evaluator.get_evaluation_id(), instructions)
                for instruction in instructions:
                    if instruction.id and instruction.reference_file:
                        presigned_url = template_service.get_presigned_url_by_template_question_id(instruction.id)
                        template_service.upload_reference_file_by_url_and_file_path(
                            presigned_url, instruction.reference_file, question_id=instruction.id
                        )

            if core_questions:
                log.debug(f"Creating {len(core_questions)} core questions...")
                core_questions = template_service.create_template_questions_by_evaluation_id_and_questions(
                    evaluator.get_evaluation_id(), core_questions
                )

            # Create options for questions that have options
            questions_with_options = [q for q in (instructions + core_questions) if q.options]
            if questions_with_options:
                log.debug(f"Creating options for {len(questions_with_options)} questions...")
                for question in questions_with_options:
                    if question.id:
                        options = template_service.create_template_options_by_question_id_and_options(question.id, question.options)
                        for option in options:
                            if option.id and option.reference_file:
                                presigned_url = template_service.get_presigned_url_by_template_option_id(option.id)
                                template_service.upload_reference_file_by_url_and_file_path(presigned_url, option.reference_file, option_id=option.id)

        except Exception as e:
            log.error(f"Failed to create template: {str(e)}")
            raise HTTPError(f"Failed to create template questions: {e}")

        log.info("Template creation completed successfully")
        return evaluator
