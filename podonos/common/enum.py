"""
Default enum values across whole SDK
"""

from enum import Enum
from typing import List


class EvalType(Enum):
    NMOS = "NMOS"
    QMOS = "QMOS"
    P808 = "P808"
    SMOS = "SMOS"
    PREF = "PREF"
    CMOS = "CMOS"
    DMOS = "DMOS"
    CUSTOM_SINGLE = "CUSTOM_SINGLE"
    CUSTOM_DOUBLE = "CUSTOM_DOUBLE"

    def get_type(self) -> str:
        if self.value in ["CUSTOM_SINGLE", "CUSTOM_DOUBLE"]:
            return "CUSTOM"
        elif self.value == "PREF":
            return "SPEECH_PREFERENCE"
        return f"SPEECH_{self.value}"

    @staticmethod
    def get_single_types() -> List["EvalType"]:
        """Get all single stimulus evaluation types"""
        return [EvalType.NMOS, EvalType.QMOS, EvalType.P808, EvalType.CUSTOM_SINGLE]

    @staticmethod
    def get_double_types() -> List["EvalType"]:
        """Get all double stimuli evaluation types"""
        return [EvalType.PREF, EvalType.SMOS, EvalType.CUSTOM_DOUBLE]

    @staticmethod
    def is_single(type_str: str) -> bool:
        """Check if type is single stimulus"""
        return EvalType(type_str) in EvalType.get_single_types()

    @staticmethod
    def is_double(type_str: str) -> bool:
        """Check if type is double stimuli"""
        return EvalType(type_str) in EvalType.get_double_types()

    @staticmethod
    def is_eval_type(eval_type: str) -> bool:
        return any([item for item in EvalType if item.value == eval_type])


class Language(Enum):
    ENGLISH_AMERICAN = "en-us"
    ENGLISH_BRITISH = "en-gb"
    ENGLISH_AUSTRALIAN = "en-au"
    ENGLISH_CANADIAN = "en-ca"
    KOREAN = "ko-kr"
    MANDARIN = "zh-cn"
    SPANISH_SPAIN = "es-es"
    SPANISH_MEXICO = "es-mx"
    FRENCH = "fr-fr"
    GERMAN = "de-de"
    JAPANESE = "ja-jp"
    ITALIAN = "it-it"
    POLISH = "pl-pl"
    AUDIO = "audio"

    @classmethod
    def from_value(cls, value):
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"{value} is not a valid value for {cls.__name__}")


class QuestionFileType(str, Enum):
    STIMULUS = "STIMULUS"
    REF = "REF"
    META = "META"


class QuestionResponseCategory(Enum):
    CHOICE_ONE = "CHOICE_ONE"
    CHOICE_MULTI = "CHOICE_MULTI"
    CHOICE_ONE_NO_SCORE = "CHOICE_ONE_NO_SCORE"
    SCALE_LINEAR = "SCALE_LINEAR"
    INSTRUCTION = "INSTRUCTION"


class QuestionUsageType(Enum):
    GUIDELINE_CORRECT = "GUIDELINE_CORRECT"
    GUIDELINE_WARNING = "GUIDELINE_WARNING"
    GUIDELINE_PROHIBIT = "GUIDELINE_PROHIBIT"
    SCORE = "SCORE"


class GuideCategory(Enum):
    CORRECT = "CORRECT"
    WARNING = "WARNING"
    PROHIBIT = "PROHIBIT"
