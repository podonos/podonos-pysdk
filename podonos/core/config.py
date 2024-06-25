import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import EvalType, Language

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class EvalConfigDefault:
    TYPE = EvalType.NMOS
    LAN = Language.EN_US
    NUM_EVAL = 3
    DUE_HOURS = 12
    AUTO_START = False
    GRANULARITY = 1.0


class EvalConfig:
    _eval_id: str 
    _eval_name: str
    _eval_expected_due: str  # Due string in ISO 8601.
    _eval_creation_timestamp: str  # Create a mission timestamp string. Use this as a prefix of uploaded filenames.
    _eval_description: Optional[str] = None
    _eval_type: EvalType = EvalConfigDefault.TYPE
    _eval_language: Language = EvalConfigDefault.LAN
    _eval_granularity: float = EvalConfigDefault.GRANULARITY
    _eval_num: int = 3
    _eval_expected_due_tzname: Optional[str] = None
    _eval_auto_start: bool = False

    def __init__(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalConfigDefault.TYPE.value,
        lan: str = EvalConfigDefault.LAN.value,
        granularity: float = EvalConfigDefault.GRANULARITY,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS,  # TODO: allow floating point hours, e.g. 0.5.
        auto_start: bool = EvalConfigDefault.AUTO_START
    ) -> None:
        self._eval_name = self._set_eval_name(name)
        self._eval_description = desc
        self._eval_type = self._set_eval_type(type)
        self._eval_language = self._set_eval_language(lan)
        self._eval_num = self._set_eval_num(num_eval)
        self._eval_granularity = self._set_eval_granularity(granularity)
        self._eval_expected_due = self._set_eval_expected_due(due_hours)
        self._eval_expected_due_tzname = self._set_eval_expected_due_tzname()
        self._eval_creation_timestamp = self._set_eval_creation_timestamp()
        self._eval_id = self._eval_creation_timestamp
        self._eval_auto_start = self._set_eval_auto_start(auto_start)
        self.log_eval_config()

    def log_eval_config(self) -> None:
        log.debug(f'Name: {self._eval_name}')
        log.debug(f'Desc: {self._eval_description}')
        log.debug(f'Eval type: {self._eval_type}')
        log.debug(f'Language: {self._eval_language}')
        log.debug(f'num_eval: {self._eval_num}')
        log.debug(f'Expected due: {self._eval_expected_due} {self._eval_expected_due_tzname}')
        log.debug(f'Evaluation ID: {self._eval_id}')
        log.debug(f'Evaluation auto start: {self._eval_auto_start}')

    @property
    def eval_id(self) -> str:
        return self._eval_id
    
    @property
    def eval_type(self) -> EvalType:
        return self._eval_type
    
    @property
    def eval_creation_timestamp(self) -> str:
        return self._eval_creation_timestamp

    @property
    def eval_auto_start(self) -> bool:
        return self._eval_auto_start
    
    @eval_id.setter
    def eval_id(self, eval_id: str) -> None:
        self._eval_id = eval_id

    def _set_eval_name(self, eval_name: Optional[str]) -> str:
        if not eval_name:
            current = datetime.now()
            return f"{current.year}{current.month}{current.day}{current.hour}{current.minute}{current.second}"
        elif len(eval_name) > 1:
            return eval_name
        else:
            raise ValueError('"name" must be longer than 1.')

    def _set_eval_type(self, eval_type: str) -> EvalType:
        if eval_type not in [EvalType.NMOS.value, EvalType.QMOS.value, EvalType.SMOS.value, EvalType.P808.value]:
            raise ValueError(
                f'"type" must be one of {{NMOS, SMOS, P808}}. \n' +
                f'Do you want other evaluation types? Let us know at {PODONOS_CONTACT_EMAIL}'
            )
        return EvalType(eval_type)

    def _set_eval_language(self, eval_language: str) -> Language:
        if eval_language not in [
            Language.EN_US.value, Language.EN_GB.value,
            Language.EN_AU.value, Language.EN_CA.value,
            Language.ES_ES.value, Language.ES_MX.value,
            Language.KO_KR.value, Language.AUDIO.value
        ]:
            raise ValueError(
                f'"lan" must be one of the supported language strings. ' +
                f'See https://docs.podonos.com/reference#create-evaluator \n' +
                f'Do you want us to support other languages? Let us know at {PODONOS_CONTACT_EMAIL}.'
            )
        return Language(eval_language)

    def _set_eval_num(self, num_eval: int) -> int:
        if num_eval < 1:
            raise ValueError(f'"num_eval" must be >= 1.')
        return num_eval

    # TODO: allow floating point hours, e.g. 0.5.
    def _set_eval_expected_due(self, due_hours: int) -> str:
        if due_hours < 12:
            raise ValueError('"due_hours" must be >=12.')

        due = datetime.now() + timedelta(hours=due_hours)
        return due.astimezone().isoformat(timespec='milliseconds')

    def _set_eval_expected_due_tzname(self) -> Optional[str]:
        return datetime.now().astimezone().tzname()

    def _set_eval_granularity(self, granularity: float) -> float:
        if granularity not in [0.5, 1.0]:
            raise ValueError(f'"granularity" must be one of 0.5 and 1.9')
        return granularity

    def _set_eval_creation_timestamp(self) -> str:
        return datetime.now().isoformat(timespec='milliseconds')

    def _set_eval_auto_start(self, eval_auto_start: bool) -> bool:
        return eval_auto_start

    def to_dict(self) -> Dict[str, Any]:
        return {
            'eval_id': self._eval_id,
            'eval_name': self._eval_name,
            'eval_description': self._eval_description,
            'eval_type': self._eval_type.value,
            'eval_language': self._eval_language.value,
            'eval_num': self._eval_num,
            'eval_expected_due': self._eval_expected_due,
            'eval_creation_timestamp': self._eval_creation_timestamp,
            'eval_auto_start': self._eval_auto_start
        }
    
    def to_create_request_dto(self) -> Dict[str, Any]:
        return {
            "title": self._eval_name,
            "internal_name": self._eval_name,
            "description": self._eval_description,
            "language": self._eval_language.value,
            "granularity": self._eval_granularity,
            "evaluation_type": self._eval_type.get_type()
        }
