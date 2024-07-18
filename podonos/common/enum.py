"""
Default enum values across whole SDK
"""
from enum import Enum


class EvalType(Enum):
    NMOS = 'NMOS'
    QMOS = "QMOS"
    P808 = 'P808'
    SMOS = 'SMOS'
    PREF = 'PREF'
    CMOS = 'CMOS'
    DMOS = 'DMOS'
    
    def get_type(self) -> str:
        if self.value == "PREF":
            return "SPEECH_PREFERENCE"
        return f"SPEECH_{self.value}"
    
    @staticmethod
    def is_eval_type(type: str) -> bool:
        return any([item for item in EvalType if item.value == type])

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
    GERNAM = "de-de"
    JAPANESE = "ja-jp"
    ITALIAN = "it-it"
    POLISH = "pl-pl"
    AUDIO = 'audio'

class QuestionFileType(str, Enum):
    STIMULUS = "STIMULUS"
    REF = "REF"