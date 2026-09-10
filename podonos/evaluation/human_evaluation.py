import os
from typing import Any, Dict, Optional, Tuple, Union

from requests import HTTPError

from podonos.common.enum import CustomType, EvalType
from podonos.common.validator import Rules, validate_args, validate_custom_type
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluator import Evaluator
from podonos.core.template import TemplateJsonLoader, TemplateValidator
from podonos.core.upload_ledger import UploadLedger
from podonos.service import EvaluationService, TemplateService


class HumanEvaluation:
    _api_client: APIClient
    _evaluation_service: EvaluationService
    _template_service: TemplateService

    def __init__(
        self,
        api_client: APIClient,
        evaluation_service: EvaluationService,
        template_service: TemplateService,
    ):
        self._api_client = api_client
        self._evaluation_service = evaluation_service
        self._template_service = template_service

    @validate_args(
        name=Rules.str_not_none_or_none,
        desc=Rules.str_not_none_or_none,
        type=Rules.str_not_none,
        lan=Rules.str_not_none,
        granularity=Rules.float_not_none,
        num_eval=Rules.int_not_none,
        due_hours=Rules.int_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.int_not_none,
        verify_batch_size=Rules.int_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
    )
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
        verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE,
        api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        resume_upload: bool = EvalConfigDefault.RESUME_UPLOAD,
        upload_state_path: Optional[str] = EvalConfigDefault.UPLOAD_STATE_PATH,
        # Appended last on purpose: inserting a parameter mid-signature silently
        # rebinds every positional argument after it.
        start_timeout: float = EvalConfigDefault.START_TIMEOUT,
    ) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://www.podonos.com/docs/reference#param-lan

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. Default: NMOS
            lan: Language code for this audio, e.g. "en-us". Any code the Podonos backend supports; common values are in Language. Default: en-us
            granularity: Granularity of the evaluation scales. Either {1, 0.5}
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 10.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_loudness_normalization: Enable loudness normalization for evaluation.
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds to wait for the evaluation to start. Must be positive. Default: 1800

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this type is not supported.
        """

        if not EvalType.is_eval_type(type):
            raise ValueError(
                "Not supported evaluation types. Use one of the "
                "{'NMOS', 'QMOS', 'P808', 'CMOS', 'SMOS', 'CSMOS', 'PREF', 'CUSTOM_SINGLE', 'CUSTOM_DOUBLE', 'RANKING', 'RANKING_REF'}"
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
            verify_batch_size=verify_batch_size,
            api_timeout=api_timeout,
            verify_timeout=verify_timeout,
            upload_timeout=upload_timeout,
            resume_upload=resume_upload,
            upload_state_path=upload_state_path,
            start_timeout=start_timeout,
        )

        if EvalType.is_double(type):
            supported_types = EvalType.get_double_types()
        elif EvalType.is_single(type):
            supported_types = EvalType.get_single_types()
        elif EvalType.is_triple(type):
            supported_types = EvalType.get_triple_types()
        elif EvalType.is_ranking(type):
            supported_types = EvalType.get_ranking_types()
        else:
            raise ValueError(f"Invalid evaluation type: {type}")

        return Evaluator(
            api_client=self._api_client,
            eval_config=eval_config,
            supported_eval_types=supported_types,
        )

    @validate_args(
        evaluation_id=Rules.uuid_not_none,
        upload_state_path=Rules.str_not_none,
        name=Rules.str_not_none_or_none,
        desc=Rules.str_not_none_or_none,
        type=Rules.str_not_none,
        lan=Rules.str_not_none,
        granularity=Rules.float_not_none,
        num_eval=Rules.int_not_none,
        due_hours=Rules.int_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.int_not_none,
        verify_batch_size=Rules.int_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
    )
    def resume(
        self,
        evaluation_id: str,
        upload_state_path: str,
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
        verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE,
        api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        start_timeout: float = EvalConfigDefault.START_TIMEOUT,
    ) -> Evaluator:
        """Resume an existing evaluation using local upload ledger state."""

        ledger_contract = self._load_resume_contract(
            evaluation_id=evaluation_id,
            upload_state_path=upload_state_path,
        )
        if ledger_contract is None:
            raise ValueError(
                "Upload ledger is missing the original evaluation contract; "
                "cannot safely resume this evaluation."
            )
        contract_batch_size: Optional[int] = None
        template_id: Optional[str] = None
        session_config = ledger_contract.get("session_config")
        if isinstance(session_config, dict):
            name = session_config.get("eval_name", name)
            desc = session_config.get("eval_description", desc)
            num_eval = int(session_config.get("eval_num", num_eval))
            restored_auto_start = self._contract_bool(
                session_config, "eval_auto_start", auto_start
            )
            if restored_auto_start != auto_start:
                # Ledgers written before 0.46.0 recorded auto_start while it did nothing, so a
                # stored True is not evidence the user wanted to be charged on resume.
                log.warning(
                    f"auto_start={restored_auto_start} restored from the resumed session, "
                    f"overriding the auto_start={auto_start} passed here. "
                    f"close() will {'start and charge for' if restored_auto_start else 'not start'} this evaluation."
                )
            auto_start = restored_auto_start
            verify_batch_size = int(
                session_config.get("verify_batch_size", verify_batch_size)
            )
        type = str(ledger_contract.get("eval_type", type))
        lan = str(ledger_contract.get("eval_language", lan))
        use_annotation = self._contract_bool(
            ledger_contract, "use_annotation", use_annotation
        )
        use_loudness_normalization = self._contract_bool(
            ledger_contract,
            "use_loudness_normalization",
            use_loudness_normalization,
        )
        template_id_value = ledger_contract.get("eval_template_id")
        template_id = (
            str(template_id_value)
            if template_id_value not in (None, "")
            else None
        )
        batch_size_value = ledger_contract.get("eval_batch_size")
        if batch_size_value is not None:
            contract_batch_size = int(batch_size_value)

        if not EvalType.is_eval_type(type):
            raise ValueError(
                "Not supported evaluation types. Use one of the "
                "{'NMOS', 'QMOS', 'P808', 'CMOS', 'SMOS', 'CSMOS', 'PREF', 'CUSTOM_SINGLE', 'CUSTOM_DOUBLE', 'RANKING', 'RANKING_REF'}"
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
            template_id=template_id,
            max_upload_workers=max_upload_workers,
            verify_batch_size=verify_batch_size,
            api_timeout=api_timeout,
            verify_timeout=verify_timeout,
            upload_timeout=upload_timeout,
            resume_upload=True,
            upload_state_path=upload_state_path,
            resume_evaluation_id=evaluation_id,
            # Unlike auto_start, the caller's start_timeout wins on resume: it is
            # never stored in the ledger, so there is nothing to restore.
            start_timeout=start_timeout,
        )
        if ledger_contract and isinstance(ledger_contract.get("session_config"), dict):
            eval_config.restore_resume_session_config(ledger_contract["session_config"])
        if contract_batch_size is not None:
            eval_config.eval_batch_size = contract_batch_size

        if EvalType.is_double(type):
            supported_types = EvalType.get_double_types()
        elif EvalType.is_single(type):
            supported_types = EvalType.get_single_types()
        elif EvalType.is_triple(type):
            supported_types = EvalType.get_triple_types()
        elif EvalType.is_ranking(type):
            supported_types = EvalType.get_ranking_types()
        else:
            raise ValueError(f"Invalid evaluation type: {type}")

        return Evaluator(
            api_client=self._api_client,
            eval_config=eval_config,
            supported_eval_types=supported_types,
        )

    def _load_resume_contract(
        self, evaluation_id: str, upload_state_path: str
    ) -> Optional[Dict[str, Any]]:
        """Read immutable resume contract so callers need not repeat it."""

        if not os.path.isfile(os.path.abspath(upload_state_path)):
            return None
        ledger = UploadLedger(upload_state_path)
        contract = ledger.get_evaluation_contract(evaluation_id)
        if contract is None:
            return None
        if not isinstance(contract.get("session_config"), dict):
            raise ValueError(
                "Upload ledger is missing the original session configuration; "
                "cannot safely resume this evaluation."
            )
        return contract

    @staticmethod
    def _contract_bool(
        contract: Dict[str, Any],
        key: str,
        fallback: bool,
    ) -> bool:
        value = contract.get(key)
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    @validate_args(
        name=Rules.str_not_none,
        template_id=Rules.str_non_empty,
        num_eval=Rules.int_not_none,
        desc=Rules.str_not_none_or_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.int_not_none,
        verify_batch_size=Rules.int_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
    )
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
        verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE,
        api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        resume_upload: bool = EvalConfigDefault.RESUME_UPLOAD,
        upload_state_path: Optional[str] = EvalConfigDefault.UPLOAD_STATE_PATH,
        start_timeout: float = EvalConfigDefault.START_TIMEOUT,
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
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds to wait for the evaluation to start. Must be positive. Default: 1800

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

        # Determine eval_type from template.evaluation_type if present, else from batch_size
        selected_eval_type = EvalType.selected_from_template_evaluation_type(
            template.evaluation_type or "CUSTOM", batch_size=template.batch_size
        )

        eval_config = EvalConfig(
            type=selected_eval_type.value,
            name=name,
            desc=desc,
            num_eval=num_eval,
            use_annotation=use_annotation,
            use_loudness_normalization=use_loudness_normalization,
            auto_start=auto_start,
            template_id=str(template.id),
            max_upload_workers=max_upload_workers,
            verify_batch_size=verify_batch_size,
            api_timeout=api_timeout,
            verify_timeout=verify_timeout,
            upload_timeout=upload_timeout,
            resume_upload=resume_upload,
            upload_state_path=upload_state_path,
            start_timeout=start_timeout,
        )

        # Derive supported types from the selected type
        supported_types = EvalType.get_supported_types_for(selected_eval_type)
        return Evaluator(
            api_client=self._api_client,
            eval_config=eval_config,
            supported_eval_types=supported_types,
        )

    @validate_args(
        json=Rules.dict_not_none_or_none,
        json_file=Rules.str_not_none_or_none,
        name=Rules.str_not_none_or_none,
        custom_type=validate_custom_type,
        desc=Rules.str_not_none_or_none,
        lan=Rules.str_not_none,
        num_eval=Rules.int_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.int_not_none,
        verify_batch_size=Rules.int_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
    )
    def create_from_template_json(
        self,
        json: Optional[Dict[str, Any]] = None,
        json_file: Optional[str] = None,
        name: Optional[str] = None,
        custom_type: Union[CustomType, str] = CustomType.SINGLE,
        desc: Optional[str] = None,
        lan: str = EvalConfigDefault.LAN.value,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
        verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE,
        api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        resume_upload: bool = EvalConfigDefault.RESUME_UPLOAD,
        upload_state_path: Optional[str] = EvalConfigDefault.UPLOAD_STATE_PATH,
        start_timeout: float = EvalConfigDefault.START_TIMEOUT,
    ) -> Evaluator:
        """Creates a new evaluator using a template JSON.

        Args:
            json: Template JSON as a dictionary. Optional if json_file is provided.
            json_file: Path to the JSON template file. Optional if json is provided.
            name: This evaluation name. Required.
            custom_type: Type of evaluation (CustomType.SINGLE, CustomType.DOUBLE, CustomType.SINGLE_REF, CustomType.RANKING, or CustomType.RANKING_REF). Also accepts string values.
            desc: Description of this evaluation. Optional.
            lan: Language for evaluation. Defaults to EvalConfigDefault.LAN.value.
            num_eval: The number of evaluators per file. Should be >=1.
            use_annotation: Enable detailed annotation on script for detailed rating reasoning.
            use_loudness_normalization: Enable loudness normalization for evaluation. Default: False
            auto_start: The evaluation start automatically if True. Otherwise, manually start in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds to wait for the evaluation to start. Must be positive. Default: 1800

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If neither json nor json_file is provided, or if both are provided
            ValueError: If custom_type is not a valid CustomType value
            ValueError: If the JSON is invalid or contains incompatible question types
            FileNotFoundError: If the json_file path doesn't exist
        """
        # Validate and normalize custom_type to enum
        if isinstance(custom_type, str):
            try:
                custom_type = CustomType.from_value(custom_type)
            except ValueError:
                raise ValueError(
                    "custom_type must be one of SINGLE, DOUBLE, SINGLE_REF, RANKING, or RANKING_REF"
                )

        if custom_type == CustomType.SINGLE:
            eval_type = EvalType.CUSTOM_SINGLE
            batch_size = 1
        elif custom_type == CustomType.DOUBLE:
            eval_type = EvalType.CUSTOM_DOUBLE
            batch_size = 2
        elif custom_type == CustomType.SINGLE_REF:
            eval_type = EvalType.CMOS
            batch_size = 2
        elif custom_type == CustomType.RANKING:
            eval_type = EvalType.RANKING
            batch_size = 2  # Placeholder; actual size set by _update_ranking_batch_size_before_upload
        elif custom_type == CustomType.RANKING_REF:
            eval_type = EvalType.RANKING_REF
            batch_size = 2  # Placeholder; actual size set by _update_ranking_batch_size_before_upload
        else:
            raise ValueError(
                "custom_type must be one of SINGLE, DOUBLE, SINGLE_REF, RANKING, or RANKING_REF"
            )
        # Load template data
        template_data = TemplateJsonLoader.load_json(json, json_file)

        # Use the validator from template.py (pass eval_type for RANKING restrictions)
        instructions, core_questions, annotations = (
            TemplateValidator.validate_and_create_questions(
                template_data, batch_size, eval_type
            )
        )
        log.info("Template JSON is validated.")

        # Mutual exclusivity check: use_annotation and explicit AnnotationQuestion cannot be used together
        if use_annotation and annotations:
            raise ValueError(
                "Cannot use both 'use_annotation=True' and explicit AnnotationQuestion objects. "
                "Set 'use_annotation=False' when providing custom annotation questions in the template JSON."
            )

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
            verify_batch_size=verify_batch_size,
            api_timeout=api_timeout,
            verify_timeout=verify_timeout,
            upload_timeout=upload_timeout,
            resume_upload=resume_upload,
            upload_state_path=upload_state_path,
            skip_default_questions=True,
            start_timeout=start_timeout,
        )
        log.info(f"Created evaluation config with type: {eval_type.value}")

        # Derive supported types from eval_type
        supported_types = EvalType.get_supported_types_for(eval_type)

        template_service = TemplateService(self._api_client)
        evaluator = Evaluator(
            api_client=self._api_client,
            eval_config=eval_config,
            supported_eval_types=supported_types,
        )
        try:
            if instructions:
                log.debug(f"Creating {len(instructions)} instructions...")
                instructions = template_service.create_template_questions_by_evaluation_id_and_questions(
                    evaluator.get_evaluation_id(), instructions
                )
                for instruction in instructions:
                    if instruction.id and instruction.reference_files:
                        template_service.upload_reference_files_by_url_and_file_paths(
                            instruction.reference_files, instruction.id
                        )

            if core_questions:
                log.debug(f"Creating {len(core_questions)} core questions...")
                core_questions = template_service.create_template_questions_by_evaluation_id_and_questions(
                    evaluator.get_evaluation_id(), core_questions
                )

            if annotations:
                log.debug(f"Creating {len(annotations)} annotation questions...")
                template_service.create_template_questions_by_evaluation_id_and_questions(
                    evaluator.get_evaluation_id(), annotations
                )

            # Create options for questions that have options
            questions_with_options = [
                q for q in (instructions + core_questions) if q.options
            ]
            if questions_with_options:
                log.debug(
                    f"Creating options for {len(questions_with_options)} questions..."
                )
                for question in questions_with_options:
                    if question.id:
                        options = template_service.create_template_options_by_question_id_and_options(
                            question.id, question.options
                        )
                        for option in options:
                            if option.id and option.reference_file:
                                presigned_url = template_service.get_presigned_url_by_template_option_id(
                                    option.id
                                )
                                template_service.upload_reference_file_by_url_and_file_path(
                                    presigned_url,
                                    option.reference_file,
                                    option_id=option.id,
                                )

        except Exception as e:
            log.error(f"Failed to create template: {str(e)}")
            raise HTTPError(f"Failed to create template questions: {e}")

        log.info("Template creation completed successfully")
        return evaluator
