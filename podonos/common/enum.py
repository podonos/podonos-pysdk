"""
Default enum values across whole SDK
"""
from enum import Enum

# Text colors on terminal
class TerminalColor(Enum):
    BOLD = '\033[1m'
    ENDC = '\033[0m'
    FAIL = '\033[91m'
    OK = '\033[92m'
    WARN = '\033[93m'

class EvalType(Enum):
    NMOS = 'NMOS'
    SMOS = 'SMOS'
    P808 = 'P808'

class Language(Enum):
    EN_US = 'en-us'
    EN_GB = 'en-gb'
    EN_AU = 'en-au'
    EN_CA = 'en-ca'
    ES_ES = 'es-es'
    ES_MX = 'es-mx'
    KO_KR = 'ko-kr'
    AUDIO = 'audio'