from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from podonos.common.enum import CustomType
from podonos.common.validator import Rules, validate_args, validate_custom_type
from podonos.core.api import APIClient
from podonos.core.base import *
from podonos.core.config import EvalConfigDefault
from podonos.core.evaluator import Evaluator
from podonos.evaluation import AIEvaluation, HumanEvaluation
from podonos.entity.evaluation import EvaluationProgress
from podonos.entity.flash_eval import FlashEvalResult
from podonos.service import (
    CollectionService,
    EvaluationService,
    FlashEvalService,
    ScriptService,
    TemplateService,
)


class Client:
    """Podonos Client class. Used for creating individual evaluator and managing the evaluations."""

    _api_client: APIClient
    _initialized: bool = False

    # Services
    _collection_service: CollectionService
    _evaluation_service: EvaluationService
    _flash_eval_service: FlashEvalService
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
        self._flash_eval_service = FlashEvalService(self._api_client)
        self._script_service = ScriptService(self._api_client)
        self._template_service = TemplateService(self._api_client)

        self._ai_evaluation = AIEvaluation(self._api_client)
        self._human_evaluation = HumanEvaluation(
            self._api_client, self._evaluation_service, self._template_service
        )

    @validate_args(
        name=Rules.str_not_none_or_none,
        desc=Rules.str_not_none_or_none,
        type=Rules.str_non_empty,
        lan=Rules.str_non_empty,
        granularity=Rules.float_not_none,
        num_eval=Rules.positive_not_none,
        due_hours=Rules.positive_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.positive_not_none,
        verify_batch_size=Rules.positive_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
    )
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
            lan: Human language for this audio. One of those in Language. Default: en-us
            granularity: Granularity of the evaluation scales. Either {1, 0.5}
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 10.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.
            use_annotation: Enable detailed annotation on script for detailed comments.
            use_loudness_normalization: Enable loudness normalization for evaluation.
            auto_start: When True, close() blocks until the uploaded files finish processing
                        and then starts the evaluation, which CHARGES your workspace balance.
                        It raises if it cannot start. When False, close() returns as soon as the
                        uploads are done and nothing is charged until you start the evaluation
                        yourself in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds close() waits when auto_start is True. Must be positive.
                        Default: 1800. This limits when the SDK stops issuing new requests;
                        a request already in flight may finish somewhat after it.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
            HTTPError: from close(), when auto_start is True and the backend refuses the start.
            TimeoutError: from close(), when auto_start is True and start_timeout elapses.
                        This is the builtin, so `except HTTPError` will not catch it.

        Pair auto_start=True with resume_upload=True and an upload_state_path. If the start
        fails or times out, resume_evaluator() is the only way back to that evaluation --
        without a ledger it cannot be resumed, close() cannot be retried, and re-running
        uploads everything again into a second evaluation. Recovering by hand means starting
        it from the web workspace.
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")
        return self._human_evaluation.create(
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

    @validate_args(
        evaluation_id=Rules.uuid_not_none,
        upload_state_path=Rules.str_non_empty,
        name=Rules.str_not_none_or_none,
        desc=Rules.str_not_none_or_none,
        type=Rules.str_non_empty,
        lan=Rules.str_non_empty,
        granularity=Rules.float_not_none,
        num_eval=Rules.positive_not_none,
        due_hours=Rules.positive_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.positive_not_none,
        verify_batch_size=Rules.positive_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
    )
    def resume_evaluator(
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
        """Resume uploads for an existing evaluation using an SDK upload ledger.

        The caller must add files again in the same order as the interrupted run
        so the ledger can recover each file's remote object identity.

        An evaluation whose upload began on an SDK version that did not normalize
        order_in_group cannot be repaired by resuming. Files already registered keep
        the order they were stored with, and only the remaining files get the
        normalized order, so the evaluation can still fail validation at checkout.
        Create a new evaluation instead.

        This is also the recovery path after a failed auto_start: an evaluation whose files
        uploaded but whose start did not complete can be resumed here, provided the original
        run used resume_upload=True with an upload_state_path.

        Args:
            auto_start: Restored from the resumed session's ledger, so the value passed here
                        is ignored. If the original run set it, close() blocks and starts the
                        evaluation -- CHARGES your workspace balance -- even when you pass
                        False. Ledgers written before 0.46.0 recorded auto_start while it did
                        nothing, so an old session may carry a True that was never intended to
                        spend anything; the SDK logs a warning when the restored value
                        disagrees with the one you passed.
            start_timeout: Seconds close() waits when the restored auto_start is True. Must be
                        positive. Default: 1800. Unlike auto_start this is NOT restored from
                        the session, so the value passed here wins. It limits when the SDK
                        stops issuing new requests; a request already in flight may finish
                        somewhat after it.

        Raises:
            ValueError: if this function is called before calling init().
            EvaluationNotFoundError: if the evaluation id is not in the API key's workspace.
                        Raised by resume_evaluator itself, not by close().
            HTTPError: from close(), when auto_start is True and the backend refuses the start.
            TimeoutError: from close(), when auto_start is True and start_timeout elapses.
                        This is the builtin, so `except HTTPError` will not catch it.
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")
        return self._human_evaluation.resume(
            evaluation_id=evaluation_id,
            upload_state_path=upload_state_path,
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
            start_timeout=start_timeout,
        )

    @validate_args(
        name=Rules.str_non_empty,
        template_id=Rules.str_non_empty,
        num_eval=Rules.positive_not_none,
        desc=Rules.str_not_none_or_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.positive_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        verify_batch_size=Rules.positive_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
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
            num_eval: The number of evaluators per file. Should be >= 1. Default: 10
            auto_start: When True, close() blocks until the uploaded files finish processing
                        and then starts the evaluation, which CHARGES your workspace balance.
                        It raises if it cannot start. When False, close() returns as soon as the
                        uploads are done and nothing is charged until you start the evaluation
                        yourself in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            use_annotation: Enable detailed annotation on script for detailed comments. Default: False
            use_loudness_normalization: Enable loudness normalization for evaluation. Default: True
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds close() waits when auto_start is True. Must be positive.
                        Default: 1800. This limits when the SDK stops issuing new requests;
                        a request already in flight may finish somewhat after it.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If the template ID is invalid or not found.
            HTTPError: from close(), when auto_start is True and the backend refuses the start.
            TimeoutError: from close(), when auto_start is True and start_timeout elapses.
                        This is the builtin, so `except HTTPError` will not catch it.
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        return self._human_evaluation.create_from_template(
            name=name,
            template_id=template_id,
            num_eval=num_eval,
            desc=desc,
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

    @validate_args(
        json=Rules.dict_not_none_or_none,
        json_file=Rules.str_not_none_or_none,
        name=Rules.str_not_none_or_none,
        custom_type=validate_custom_type,
        desc=Rules.str_not_none_or_none,
        lan=Rules.str_non_empty,
        num_eval=Rules.positive_not_none,
        use_annotation=Rules.bool_not_none,
        use_loudness_normalization=Rules.bool_not_none,
        auto_start=Rules.bool_not_none,
        max_upload_workers=Rules.positive_not_none,
        verify_batch_size=Rules.positive_not_none,
        api_timeout=Rules.make_type_rule((tuple, list)),
        verify_timeout=Rules.make_type_rule((tuple, list)),
        upload_timeout=Rules.make_type_rule((tuple, list)),
        resume_upload=Rules.bool_not_none,
        upload_state_path=Rules.str_not_none_or_none,
    )
    def create_evaluator_from_template_json(
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
            auto_start: When True, close() blocks until the uploaded files finish processing
                        and then starts the evaluation, which CHARGES your workspace balance.
                        It raises if it cannot start. When False, close() returns as soon as the
                        uploads are done and nothing is charged until you start the evaluation
                        yourself in the workspace.
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
            verify_batch_size: The batch size for file verification API calls. Must be 1-1000. Default: 100
            api_timeout: Default API timeout tuple. Default: (5, 30)
            verify_timeout: File verification timeout tuple. Default: (5, 120)
            upload_timeout: Direct upload timeout tuple. Default: (10, 300)
            resume_upload: Enable SDK-local upload ledger/resume. Default: False
            upload_state_path: Optional SQLite ledger path when resume_upload is enabled.
            start_timeout: Seconds close() waits when auto_start is True. Must be positive.
                        Default: 1800. This limits when the SDK stops issuing new requests;
                        a request already in flight may finish somewhat after it.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: If neither json nor json_file is provided, or if both are provided
            ValueError: If custom_type is not a valid CustomType value
            ValueError: If the JSON is invalid or contains incompatible question types
            HTTPError: from close(), when auto_start is True and the backend refuses the start.
            TimeoutError: from close(), when auto_start is True and start_timeout elapses.
                        This is the builtin, so `except HTTPError` will not catch it.
            FileNotFoundError: If the json_file path doesn't exist
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        return self._human_evaluation.create_from_template_json(
            json=json,
            json_file=json_file,
            name=name,
            custom_type=custom_type,
            desc=desc,
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
            start_timeout=start_timeout,
        )

    @validate_args(
        file_path=Rules.file_path_not_none,
        language=Rules.str_non_empty_or_none,
        category=Rules.str_non_empty_or_none,
    )
    def flash_eval(
        self,
        file_path: str,
        language: Optional[str] = None,
        category: Optional[str] = None,
    ) -> FlashEvalResult:
        """Runs auto-evaluation on an audio file and returns the score.

        Example:
            >>> import podonos
            >>> client = podonos.init(api_key="YOUR_API_KEY")
            >>> result = client.flash_eval(file_path="path/to/audio.wav")
            >>> print(result.naturalness)
            3.58

            # For Spanish (es-es) audio:
            >>> result = client.flash_eval(file_path="path/to/audio_es.wav", language="es-es")

            # For noise quality measurement (language is ignored when category="noise_quality"):
            >>> result = client.flash_eval(file_path="path/to/audio.wav", category="noise_quality")
            >>> print(result.noise_quality)
            3.5

        Args:
            file_path: Path to the audio file to evaluate.
            language: Language code for model routing (e.g. 'es-es').
                      When omitted, the default en-us model is used.
                      Currently available: 'en-us', 'es-es'.
                      Ignored when category is 'noise_quality'.
            category: Evaluation category. Defaults to 'naturalness' when omitted.
                      Currently available: 'naturalness', 'noise_quality'.

        Returns:
            FlashEvalResult. For category='naturalness' the `naturalness` field
            is populated; for category='noise_quality' the `noise_quality` field
            is populated.

        Raises:
            ValueError: if this function is called before calling init().
        """
        if not self._initialized:
            raise ValueError("This function is called before initialization.")
        return self._flash_eval_service.eval(file_path, language=language, category=category)

    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Each row carries `progress` (0 to 100), `internal_status`, `started_time` and
        `ended_time` alongside the evaluation's identity, so a completed evaluation can be
        detected without opening the web app.

        Completion is `status == "COMPLETED"`, never `progress >= 100`. Progress is capped at
        90 while an evaluation is running and is also 90 during report review, so it cannot
        tell "almost done" from "done" and never reaches 100 before the status flips. Gate
        automation on the status and use progress for display only.

        All four fields can be None. `started_time` and `ended_time` are None until the
        evaluation starts and ends; `progress` and `internal_status` are None on a backend
        that does not report them yet, so guard before comparing.

        To poll a single evaluation rather than the whole workspace, use
        get_evaluation_progress().

        Args: None

        Returns:
            Evaluation containing all the evaluation info
        """
        return self._evaluation_service.get_evaluation_list()

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def get_evaluation_progress(self, evaluation_id: str) -> EvaluationProgress:
        """Gets the status and progress of one evaluation.

        Completion is `status == "COMPLETED"`, never `progress >= 100`, for the reason given
        in get_evaluation_list(). `COMPLETED`, `CANCELED` and `DELETED` are the states worth
        stopping a poll on; a deleted or hidden evaluation still reports its real status here
        rather than disappearing the way it does from get_evaluation_list().

        The backend allows 60 requests per minute per API key, counted across every evaluation
        id rather than per evaluation. Polling N evaluations therefore wants an interval of at
        least N seconds. A 429 is retried with backoff by the transport, and those retries
        count against the same budget; a sustained 429 surfaces as an `HTTPError` with
        status 429 once the retries are exhausted.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.

        Returns:
            EvaluationProgress for the evaluation.

        Raises:
            EvaluationNotFoundError: if the id is not in this API key's workspace. The backend
                       answers this as 401 rather than 404 so it never reveals whether the id
                       exists somewhere else.
            HTTPError: on any other failure. A 401 for a missing or revoked key stays an
                       HTTPError so it is not mistaken for a deleted evaluation, and a 404
                       means the backend does not serve evaluation progress yet.
        """
        return self._evaluation_service.get_evaluation_progress(evaluation_id)

    @validate_args(evaluation_id=Rules.uuid_not_none, group_by=Rules.str_non_empty)
    def get_stats_json_by_id(
        self,
        evaluation_id: str,
        group_by: Literal["question", "script", "model"] = "question",
    ) -> List[Dict[str, Any]]:
        """Gets a list of evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            group_by: Group by question or script. Default: "question".
                      "script" and "model" are only available for single-question evaluation.

        Returns:
            List of statistics for the evaluation.
        """
        return self._evaluation_service.get_stats_json_by_id(evaluation_id, group_by)

    @validate_args(evaluation_id=Rules.uuid_not_none, output_dir=Rules.str_not_none)
    def download_evaluation_files_by_evaluation_id(
        self, evaluation_id: str, output_dir: str
    ) -> str:
        """Download evaluation files"""
        return self._evaluation_service.download_evaluation_files_by_evaluation_id(
            evaluation_id, output_dir
        )

    @validate_args(template_id=Rules.str_non_empty)
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
            raise ValueError(
                f"Cannot find the template. Please check the id {template_id}."
            )
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
