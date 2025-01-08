"""
Default enum values across whole SDK
"""

from enum import Enum


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
    def is_eval_type(eval_type: str) -> bool:
        return any([item for item in EvalType if item.value == eval_type])

    @staticmethod
    def is_single(eval_type: str) -> bool:
        return eval_type in ["NMOS", "QMOS", "P808", "CUSTOM_SINGLE"]


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
