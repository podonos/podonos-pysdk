import os
import re
import uuid
import math
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import AIEvalType, EvalType, Language
from podonos.common.redaction import mask_secret
from podonos.common.validator import Rules, validate_args
from podonos.core.base import *


class EvalConfigDefault:
    TYPE = EvalType.NMOS
    LAN = Language.ENGLISH_AMERICAN
    NUM_EVAL = 10
    DUE_HOURS = 12
    USE_ANNOTATION = False
    USE_LOUDNESS_NORMALIZATION = True
    USE_AUTO_ANALYSIS = False
    AUTO_START = False
    START_TIMEOUT = 1800
    GRANULARITY = 1.0
    BATCH_SIZE = 1
    MAX_UPLOAD_WORKERS = 20
    VERIFY_BATCH_SIZE = 100
    API_TIMEOUT = (5, 30)
    VERIFY_TIMEOUT = (5, 120)
    UPLOAD_TIMEOUT = (10, 300)
    RESUME_UPLOAD = False
    UPLOAD_STATE_PATH = None


class EvalConfig:
    _eval_id: str
    _eval_name: str
    _eval_expected_due: str  # Due string in ISO 8601.
    _eval_creation_timestamp: str  # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
    _eval_description: Optional[str] = None
    _eval_type: EvalType = EvalConfigDefault.TYPE
    _eval_ai_type: Optional[AIEvalType] = None
    _eval_language: str = EvalConfigDefault.LAN.value
    _eval_granularity: float = EvalConfigDefault.GRANULARITY
    _eval_batch_size: int = EvalConfigDefault.BATCH_SIZE
    _eval_num: int = EvalConfigDefault.NUM_EVAL
    _eval_expected_due_tzname: Optional[str] = None
    _eval_use_annotation: bool = False
    _eval_use_loudness_normalization: bool = (
        EvalConfigDefault.USE_LOUDNESS_NORMALIZATION
    )
    _eval_auto_start: bool = False
    _eval_start_timeout: float = EvalConfigDefault.START_TIMEOUT
    _eval_template_id: Optional[str] = None
    _skip_default_questions: bool = False
    _max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS
    _verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE
    _api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT
    _verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT
    _upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT
    _resume_upload: bool = EvalConfigDefault.RESUME_UPLOAD
    _upload_state_path: Optional[str] = EvalConfigDefault.UPLOAD_STATE_PATH
    _resume_evaluation_id: Optional[str] = None

    def __init__(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalConfigDefault.TYPE.value,
        lan: str = EvalConfigDefault.LAN.value,
        ai_type: Optional[AIEvalType] = None,
        granularity: float = EvalConfigDefault.GRANULARITY,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS,  # TODO: allow floating point hours, e.g. 0.5.
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        use_loudness_normalization: bool = EvalConfigDefault.USE_LOUDNESS_NORMALIZATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        template_id: Optional[str] = None,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
        verify_batch_size: int = EvalConfigDefault.VERIFY_BATCH_SIZE,
        api_timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        verify_timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        upload_timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        resume_upload: bool = EvalConfigDefault.RESUME_UPLOAD,
        upload_state_path: Optional[str] = EvalConfigDefault.UPLOAD_STATE_PATH,
        resume_evaluation_id: Optional[str] = None,
        skip_default_questions: bool = False,
        # Appended last on purpose: inserting a parameter mid-signature silently
        # rebinds every positional argument after it.
        start_timeout: float = EvalConfigDefault.START_TIMEOUT,
    ) -> None:
        self._eval_name = self._valudate_eval_name(name)
        self._eval_description = desc
        self._eval_type = self._validate_eval_type(type)
        self._eval_language = self._validate_eval_language(lan)
        self._eval_ai_type = self._validate_eval_ai_type(ai_type)
        self._eval_num = self._validate_eval_num(num_eval)
        self._eval_granularity = self._validate_eval_granularity(granularity)
        self._eval_batch_size = self._validate_eval_batch_size(type)
        self._eval_expected_due = self._validate_eval_expected_due(due_hours)
        self._eval_expected_due_tzname = self._validate_eval_expected_due_tzname()
        self._eval_creation_timestamp = self._validate_eval_creation_timestamp()
        self._eval_id = self._eval_creation_timestamp
        self._eval_use_annotation = self._validate_eval_use_annotation(
            use_annotation, type
        )
        self._eval_use_loudness_normalization = use_loudness_normalization
        self._eval_auto_start = auto_start
        self._eval_start_timeout = self._validate_start_timeout(start_timeout)
        self._eval_template_id = template_id
        self._max_upload_workers = max_upload_workers
        self._verify_batch_size = self._validate_verify_batch_size(verify_batch_size)
        self._api_timeout = self._validate_timeout(api_timeout, "api_timeout")
        self._verify_timeout = self._validate_timeout(verify_timeout, "verify_timeout")
        self._upload_timeout = self._validate_timeout(upload_timeout, "upload_timeout")
        self._resume_upload = self._validate_resume_upload(resume_upload)
        self._upload_state_path = self._validate_upload_state_path(upload_state_path)
        self._resume_evaluation_id = self._validate_resume_evaluation_id(
            resume_evaluation_id
        )
        self._skip_default_questions = skip_default_questions
        self.log_eval_config()

    def log_eval_config(self) -> None:
        log.debug(f"Name: {self._eval_name}")
        log.debug(f"Desc: {self._eval_description}")
        log.debug(f"Eval type: {self._eval_type}")
        log.debug(f"Language: {self._eval_language}")
        log.debug(f"AI type: {self._eval_ai_type}")
        log.debug(f"num_eval: {self._eval_num}")
        log.debug(
            f"Expected due: {self._eval_expected_due} {self._eval_expected_due_tzname}"
        )
        log.debug(f"Evaluation ID: {self._eval_id}")
        log.debug(f"Evaluation use annotation: {self._eval_use_annotation}")
        log.debug(
            f"Evaluation use loudness normalization: {self._eval_use_loudness_normalization}"
        )
        log.debug(f"Evaluation auto start: {self._eval_auto_start}")
        log.debug(f"Evaluation start timeout: {self._eval_start_timeout}")
        log.debug(f"Evaluation Template ID: {self._eval_template_id}")
        log.debug(f"Max upload workers: {self._max_upload_workers}")
        log.debug(f"Verify batch size: {self._verify_batch_size}")
        log.debug(f"API timeout: {self._api_timeout}")
        log.debug(f"Verify timeout: {self._verify_timeout}")
        log.debug(f"Upload timeout: {self._upload_timeout}")
        log.debug(f"Resume upload: {self._resume_upload}")
        upload_state_display = (
            os.path.basename(self._upload_state_path)
            if self._upload_state_path
            else None
        )
        resume_id_display = (
            mask_secret(self._resume_evaluation_id)
            if self._resume_evaluation_id
            else None
        )
        log.debug(f"Upload state path basename: {upload_state_display}")
        log.debug(f"Resume evaluation id: {resume_id_display}")
        log.debug(f"Skip default questions: {self._skip_default_questions}")

    @property
    def eval_id(self) -> str:
        return self._eval_id

    @property
    def eval_language(self) -> str:
        return self._eval_language

    @property
    def eval_type(self) -> EvalType:
        return self._eval_type

    @property
    def eval_ai_type(self) -> Optional[AIEvalType]:
        return self._eval_ai_type

    @property
    def eval_creation_timestamp(self) -> str:
        return self._eval_creation_timestamp

    @property
    def eval_use_annotation(self) -> bool:
        return self._eval_use_annotation

    @property
    def eval_auto_start(self) -> bool:
        return self._eval_auto_start

    @property
    def eval_start_timeout(self) -> float:
        return self._eval_start_timeout

    @property
    def eval_template_id(self) -> Optional[str]:
        return self._eval_template_id

    @property
    def use_loudness_normalization(self) -> bool:
        return self._eval_use_loudness_normalization

    @property
    def max_upload_workers(self) -> int:
        return self._max_upload_workers

    @property
    def verify_batch_size(self) -> int:
        return self._verify_batch_size

    @property
    def api_timeout(self) -> Tuple[float, float]:
        return self._api_timeout

    @property
    def verify_timeout(self) -> Tuple[float, float]:
        return self._verify_timeout

    @property
    def upload_timeout(self) -> Tuple[float, float]:
        return self._upload_timeout

    @property
    def resume_upload(self) -> bool:
        return self._resume_upload

    @property
    def upload_state_path(self) -> Optional[str]:
        return self._upload_state_path

    @property
    def resume_evaluation_id(self) -> Optional[str]:
        return self._resume_evaluation_id

    def resolve_upload_state_path(self) -> str:
        """Return the local ledger path when opt-in resume_upload is enabled.

        The default path is deterministic and SDK-local. Calling this method does
        not create a file; the SQLite ledger is created only if integration code
        instantiates UploadLedger while resume_upload is enabled.
        """
        if self._upload_state_path:
            return self._upload_state_path
        return os.path.join(os.getcwd(), ".podonos_upload_state.sqlite")

    @property
    def eval_batch_size(self) -> int:
        return self._eval_batch_size

    @eval_id.setter
    def eval_id(self, eval_id: str) -> None:
        self._eval_id = eval_id

    @eval_batch_size.setter
    def eval_batch_size(self, eval_batch_size: int) -> None:
        self._eval_batch_size = eval_batch_size

    @validate_args(eval_name=Rules.str_non_empty_or_none)
    def _valudate_eval_name(self, eval_name: Optional[str]) -> str:
        if not eval_name:
            current = datetime.now()
            return f"{current.year}{current.month}{current.day}{current.hour}{current.minute}{current.second}"
        elif len(eval_name) > 1:
            return eval_name
        else:
            raise ValueError('"name" must be longer than 1.')

    @validate_args(eval_type=Rules.str_non_empty)
    def _validate_eval_type(self, eval_type: str) -> EvalType:
        if eval_type not in [
            EvalType.NMOS.value,
            EvalType.QMOS.value,
            EvalType.CMOS.value,
            EvalType.SMOS.value,
            EvalType.P808.value,
            EvalType.PREF.value,
            EvalType.CSMOS.value,
            EvalType.CUSTOM_SINGLE.value,
            EvalType.CUSTOM_DOUBLE.value,
            EvalType.RANKING.value,
            EvalType.RANKING_REF.value,
        ]:
            raise ValueError(
                '"type" must be one of {NMOS, QMOS, CMOS, CSMOS, SMOS, P808, PREF, CUSTOM_SINGLE, CUSTOM_DOUBLE, RANKING, RANKING_REF}. \n'
                + f"Do you want other evaluation types? Let us know at {PODONOS_CONTACT_EMAIL}"
            )
        return EvalType(eval_type)

    @validate_args(eval_language=Rules.str_non_empty)
    def _validate_eval_language(self, eval_language: str) -> str:
        # Shape check only. The backend is the source of truth for which languages exist and
        # rejects unknown codes, so we deliberately do NOT keep a hardcoded language list here —
        # new languages need no SDK release. We normalize case (backend codes are lowercase) and
        # reject anything that isn't a locale-shaped code (e.g. "en-us") or the special "audio".
        # The Language enum remains available as convenience constants.
        code = eval_language.strip().lower()
        if code != Language.AUDIO.value and not re.fullmatch(r"[a-z]{2,3}-[a-z]{2,4}", code):
            raise ValueError(
                f'"lan" ({eval_language!r}) does not look like a language code. '
                + 'Use a locale code such as "en-us" or "ko-kr". '
                + "See https://www.podonos.com/docs/reference#create-evaluator \n"
                + f"Do you want us to support other languages? Let us know at {PODONOS_CONTACT_EMAIL}."
            )
        return code

    @validate_args(eval_ai_type=Rules.optional_instance_of(AIEvalType))
    def _validate_eval_ai_type(
        self, eval_ai_type: Optional[AIEvalType]
    ) -> Optional[AIEvalType]:
        if eval_ai_type and eval_ai_type not in [AIEvalType.ALL]:
            raise ValueError('"ai_type" must be one of {ALL}.')
        return eval_ai_type

    @validate_args(num_eval=Rules.positive_not_none)
    def _validate_eval_num(self, num_eval: int) -> int:
        if num_eval < 1:
            raise ValueError('"num_eval" must be >= 1.')
        return num_eval

    @validate_args(granularity=Rules.float_not_none)
    def _validate_eval_granularity(self, granularity: float) -> float:
        if granularity not in [0.5, 1.0]:
            raise ValueError('"granularity" must be one of 0.5 and 1.0')
        return granularity

    @validate_args(eval_type=Rules.str_non_empty)
    def _validate_eval_batch_size(self, eval_type: str) -> int:
        if EvalType.is_single(eval_type):
            return 1
        elif EvalType.is_double(eval_type):
            return 2
        elif EvalType.is_triple(eval_type):
            return 3
        elif EvalType.is_ranking(eval_type):
            # Placeholder; the real size is sent by _update_ranking_batch_size_before_upload.
            # It still has to clear the minimum the service accepts at creation time:
            # 2 for a plain ranking, 3 for one with a reference (2 stimuli + 1 ref).
            return 3 if EvalType(eval_type) == EvalType.RANKING_REF else 2
        else:
            raise ValueError(
                '"eval_type" must be one of {NMOS, QMOS, P808, CMOS, SMOS, PREF, CSMOS, CUSTOM_SINGLE, CUSTOM_DOUBLE, RANKING, RANKING_REF}.'
            )

    # TODO: allow floating point hours, e.g. 0.5.
    @validate_args(due_hours=Rules.positive_not_none)
    def _validate_eval_expected_due(self, due_hours: int) -> str:
        if due_hours < 12:
            raise ValueError('"due_hours" must be >=12.')

        due = datetime.now() + timedelta(hours=due_hours)
        return due.astimezone().isoformat(timespec="milliseconds")

    def _validate_eval_expected_due_tzname(self) -> Optional[str]:
        return datetime.now().astimezone().tzname()

    def _validate_eval_creation_timestamp(self) -> str:
        return datetime.now().isoformat(timespec="milliseconds")

    @validate_args(
        eval_use_annotation=Rules.bool_not_none, eval_type=Rules.str_non_empty
    )
    def _validate_eval_use_annotation(
        self, eval_use_annotation: bool, eval_type: str
    ) -> bool:
        if eval_use_annotation and eval_type not in [
            EvalType.NMOS.value,
            EvalType.QMOS.value,
            EvalType.P808.value,
            EvalType.CUSTOM_SINGLE.value,
        ]:
            raise ValueError(
                '"eval_type" must be one of {NMOS, QMOS, P808, CUSTOM_SINGLE} when using "use_annotation"'
            )
        return eval_use_annotation

    @validate_args(verify_batch_size=Rules.positive_not_none)
    def _validate_verify_batch_size(self, verify_batch_size: int) -> int:
        if verify_batch_size < 1:
            raise ValueError('"verify_batch_size" must be >= 1.')
        if verify_batch_size > 1000:
            raise ValueError('"verify_batch_size" must be <= 1000.')
        return verify_batch_size

    def _validate_timeout(
        self, timeout: Tuple[float, float], name: str
    ) -> Tuple[float, float]:
        if not isinstance(timeout, (tuple, list)) or len(timeout) != 2:
            raise ValueError(f'"{name}" must be a 2-item tuple/list: (connect_timeout, read_timeout).')

        connect_timeout, read_timeout = timeout
        if isinstance(connect_timeout, bool) or isinstance(read_timeout, bool):
            raise ValueError(f'"{name}" values must be positive numbers.')
        if not isinstance(connect_timeout, (int, float)) or not isinstance(
            read_timeout, (int, float)
        ):
            raise ValueError(f'"{name}" values must be numbers.')
        if not math.isfinite(float(connect_timeout)) or not math.isfinite(
            float(read_timeout)
        ):
            raise ValueError(f'"{name}" values must be finite.')
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError(f'"{name}" values must be positive.')
        if connect_timeout > read_timeout:
            raise ValueError(f'"{name}" connect timeout must be <= read timeout.')

        return (connect_timeout, read_timeout)

    def _validate_start_timeout(self, start_timeout: float) -> float:
        if isinstance(start_timeout, bool):
            raise ValueError('"start_timeout" must be a positive number.')
        if not isinstance(start_timeout, (int, float)):
            raise ValueError('"start_timeout" must be a number.')
        if not math.isfinite(float(start_timeout)):
            raise ValueError('"start_timeout" must be finite.')
        if start_timeout <= 0:
            raise ValueError('"start_timeout" must be positive.')
        return start_timeout

    def restore_resume_session_config(self, session_config: Dict[str, Any]) -> None:
        """Restore original session.json fields from a trusted upload ledger contract."""

        if not isinstance(session_config, dict) or not session_config:
            raise ValueError("session_config must be a non-empty dictionary")

        self._eval_name = str(session_config.get("eval_name", self._eval_name))
        self._eval_description = session_config.get(
            "eval_description", self._eval_description
        )
        self._eval_num = int(session_config.get("eval_num", self._eval_num))
        self._eval_expected_due = str(
            session_config.get("eval_expected_due", self._eval_expected_due)
        )
        self._eval_creation_timestamp = str(
            session_config.get(
                "eval_creation_timestamp", self._eval_creation_timestamp
            )
        )
        self._eval_use_annotation = bool(
            session_config.get("eval_use_annotation", self._eval_use_annotation)
        )
        self._eval_auto_start = bool(
            session_config.get("eval_auto_start", self._eval_auto_start)
        )
        self._eval_template_id = session_config.get(
            "eval_template_id", self._eval_template_id
        )
        self._eval_use_loudness_normalization = bool(
            session_config.get(
                "use_loudness_normalization",
                self._eval_use_loudness_normalization,
            )
        )
        self._max_upload_workers = int(
            session_config.get("max_upload_workers", self._max_upload_workers)
        )
        self._verify_batch_size = self._validate_verify_batch_size(
            int(session_config.get("verify_batch_size", self._verify_batch_size))
        )

    def _validate_resume_upload(self, resume_upload: bool) -> bool:
        if not isinstance(resume_upload, bool):  # type: ignore
            raise ValueError('"resume_upload" must be a boolean.')
        return resume_upload

    def _validate_upload_state_path(
        self, upload_state_path: Optional[str]
    ) -> Optional[str]:
        if upload_state_path is None:
            return None
        if not isinstance(upload_state_path, str) or not upload_state_path.strip():
            raise ValueError('"upload_state_path" must be a non-empty string or None.')
        return upload_state_path

    def _validate_resume_evaluation_id(
        self, resume_evaluation_id: Optional[str]
    ) -> Optional[str]:
        if resume_evaluation_id is None:
            return None
        if not isinstance(resume_evaluation_id, str) or not resume_evaluation_id.strip():
            raise ValueError(
                '"resume_evaluation_id" must be a non-empty string or None.'
            )
        try:
            uuid.UUID(resume_evaluation_id)
        except ValueError as exc:
            raise ValueError('"resume_evaluation_id" must be a valid UUID.') from exc
        return resume_evaluation_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eval_id": self._eval_id,
            "eval_name": self._eval_name,
            "eval_description": self._eval_description,
            "eval_type": self._eval_type.value,
            "eval_language": self._eval_language,
            "eval_num": self._eval_num,
            "eval_expected_due": self._eval_expected_due,
            "eval_creation_timestamp": self._eval_creation_timestamp,
            "eval_use_annotation": self._eval_use_annotation,
            "eval_auto_start": self._eval_auto_start,
            "eval_template_id": self._eval_template_id,
            "use_loudness_normalization": self._eval_use_loudness_normalization,
            "max_upload_workers": self._max_upload_workers,
            "verify_batch_size": self._verify_batch_size,
        }

    def to_create_request_dto(self) -> Dict[str, Any]:
        return {
            "title": self._eval_name,
            "internal_name": self._eval_name,
            "description": self._eval_description,
            "language": self._eval_language,
            "num_required_etors": self._eval_num,
            "granularity": self._eval_granularity,
            "evaluation_type": self._eval_type.get_type(),
            "batch_size": self._eval_batch_size,
            "use_annotation": self._eval_use_annotation,
            "use_loudness_normalization": self._eval_use_loudness_normalization,
            "auto_start": self._eval_auto_start,
            "skip_default_questions": self._skip_default_questions,
        }

    def to_create_from_template_request_dto(self) -> Dict[str, Any]:
        return {
            "template_id": self._eval_template_id,
            "title": self._eval_name,
            "description": self._eval_description,
            "num_required_etors": self._eval_num,
            "auto_start": self._eval_auto_start,
        }
