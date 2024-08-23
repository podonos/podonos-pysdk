from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from podonos.core.base import *
from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import EvalType, Language


class EvalConfigDefault:
    TYPE = EvalType.NMOS
    LAN = Language.ENGLISH_AMERICAN
    NUM_EVAL = 10
    DUE_HOURS = 12
    USE_ANNOTATION = False
    AUTO_START = False
    GRANULARITY = 1.0
    MAX_UPLOAD_WORKERS = 10


class EvalConfig:
    _eval_id: str
    _eval_name: str
    _eval_expected_due: str  # Due string in ISO 8601.
    _eval_creation_timestamp: str  # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
    _eval_description: Optional[str] = None
    _eval_type: EvalType = EvalConfigDefault.TYPE
    _eval_language: Language = EvalConfigDefault.LAN
    _eval_granularity: float = EvalConfigDefault.GRANULARITY
    _eval_num: int = EvalConfigDefault.NUM_EVAL
    _eval_expected_due_tzname: Optional[str] = None
    _eval_use_annotation: bool = False
    _eval_auto_start: bool = False
    _max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS

    def __init__(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalConfigDefault.TYPE.value,
        lan: str = EvalConfigDefault.LAN.value,
        granularity: float = EvalConfigDefault.GRANULARITY,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS,  # TODO: allow floating point hours, e.g. 0.5.
        use_annotation: bool = EvalConfigDefault.USE_ANNOTATION,
        auto_start: bool = EvalConfigDefault.AUTO_START,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> None:
        self._eval_name = self._valudate_eval_name(name)
        self._eval_description = desc
        self._eval_type = self._validate_eval_type(type)
        self._eval_language = self._validate_eval_language(lan)
        self._eval_num = self._validate_eval_num(num_eval)
        self._eval_granularity = self._validate_eval_granularity(granularity)
        self._eval_expected_due = self._validate_eval_expected_due(due_hours)
        self._eval_expected_due_tzname = self._validate_eval_expected_due_tzname()
        self._eval_creation_timestamp = self._validate_eval_creation_timestamp()
        self._eval_id = self._eval_creation_timestamp
        self._eval_use_annotation = self._validate_eval_use_annotation(use_annotation, type)
        self._eval_auto_start = auto_start
        self._max_upload_workers = max_upload_workers
        self.log_eval_config()

    def log_eval_config(self) -> None:
        log.debug(f"Name: {self._eval_name}")
        log.debug(f"Desc: {self._eval_description}")
        log.debug(f"Eval type: {self._eval_type}")
        log.debug(f"Language: {self._eval_language}")
        log.debug(f"num_eval: {self._eval_num}")
        log.debug(f"Expected due: {self._eval_expected_due} {self._eval_expected_due_tzname}")
        log.debug(f"Evaluation ID: {self._eval_id}")
        log.debug(f"Evaluation use annotation: {self._eval_use_annotation}")
        log.debug(f"Evaluation auto start: {self._eval_auto_start}")
        log.debug(f"Max upload workers: {self._max_upload_workers}")

    @property
    def eval_id(self) -> str:
        return self._eval_id

    @property
    def eval_language(self) -> Language:
        return self._eval_language

    @property
    def eval_type(self) -> EvalType:
        return self._eval_type

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
    def max_upload_workers(self) -> int:
        return self._max_upload_workers

    @eval_id.setter
    def eval_id(self, eval_id: str) -> None:
        self._eval_id = eval_id

    def _valudate_eval_name(self, eval_name: Optional[str]) -> str:
        if not eval_name:
            current = datetime.now()
            return f"{current.year}{current.month}{current.day}{current.hour}{current.minute}{current.second}"
        elif len(eval_name) > 1:
            return eval_name
        else:
            raise ValueError('"name" must be longer than 1.')

    def _validate_eval_type(self, eval_type: str) -> EvalType:
        if eval_type not in [
            EvalType.NMOS.value,
            EvalType.QMOS.value,
            EvalType.SMOS.value,
            EvalType.P808.value,
            EvalType.PREF.value,
        ]:
            raise ValueError(
                f'"type" must be one of {{NMOS, QMOS, SMOS, P808}}. \n'
                + f"Do you want other evaluation types? Let us know at {PODONOS_CONTACT_EMAIL}"
            )
        return EvalType(eval_type)

    def _validate_eval_language(self, eval_language: str) -> Language:
        if eval_language not in [
            Language.ENGLISH_AMERICAN.value,
            Language.ENGLISH_AUSTRALIAN.value,
            Language.ENGLISH_BRITISH.value,
            Language.ENGLISH_CANADIAN.value,
            Language.KOREAN.value,
            Language.MANDARIN.value,
            Language.SPANISH_SPAIN.value,
            Language.SPANISH_MEXICO.value,
            Language.FRENCH.value,
            Language.GERMAN.value,
            Language.JAPANESE.value,
            Language.ITALIAN.value,
            Language.POLISH.value,
            Language.AUDIO.value,
        ]:
            raise ValueError(
                f'"lan" must be one of the supported language strings. '
                + f"See https://www.podonos.com/docs/reference#create-evaluator \n"
                + f"Do you want us to support other languages? Let us know at {PODONOS_CONTACT_EMAIL}."
            )
        return Language(eval_language)

    def _validate_eval_num(self, num_eval: int) -> int:
        if num_eval < 1:
            raise ValueError(f'"num_eval" must be >= 1.')
        return num_eval

    def _validate_eval_granularity(self, granularity: float) -> float:
        if granularity not in [0.5, 1.0]:
            raise ValueError(f'"granularity" must be one of 0.5 and 1.9')
        return granularity

    # TODO: allow floating point hours, e.g. 0.5.
    def _validate_eval_expected_due(self, due_hours: int) -> str:
        if due_hours < 12:
            raise ValueError('"due_hours" must be >=12.')

        due = datetime.now() + timedelta(hours=due_hours)
        return due.astimezone().isoformat(timespec="milliseconds")

    def _validate_eval_expected_due_tzname(self) -> Optional[str]:
        return datetime.now().astimezone().tzname()

    def _validate_eval_creation_timestamp(self) -> str:
        return datetime.now().isoformat(timespec="milliseconds")

    def _validate_eval_use_annotation(self, eval_use_annotation: bool, eval_type: str) -> bool:
        if eval_use_annotation and eval_type not in [
            EvalType.NMOS.value,
            EvalType.QMOS.value,
            EvalType.P808.value,
        ]:
            raise ValueError(f'"eval_type" must be one of {{NMOS, QMOS, P808}} when using "use_annotation"')
        return eval_use_annotation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eval_id": self._eval_id,
            "eval_name": self._eval_name,
            "eval_description": self._eval_description,
            "eval_type": self._eval_type.value,
            "eval_language": self._eval_language.value,
            "eval_num": self._eval_num,
            "eval_expected_due": self._eval_expected_due,
            "eval_creation_timestamp": self._eval_creation_timestamp,
            "eval_use_annotation": self._eval_use_annotation,
            "eval_auto_start": self._eval_auto_start,
            "max_upload_workers": self._max_upload_workers,
        }

    def to_create_request_dto(self) -> Dict[str, Any]:
        return {
            "title": self._eval_name,
            "internal_name": self._eval_name,
            "description": self._eval_description,
            "language": self._eval_language.value,
            "num_required_etors": self._eval_num,
            "granularity": self._eval_granularity,
            "evaluation_type": self._eval_type.get_type(),
            "use_annotation": self._eval_use_annotation,
        }
