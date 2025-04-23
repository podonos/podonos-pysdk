"""
Default enum values across whole SDK
"""

from enum import Enum
from typing import List


class EvalType(Enum):
    # Human evaluation types
    NMOS = "NMOS"
    QMOS = "QMOS"
    P808 = "P808"
    SMOS = "SMOS"
    PREF = "PREF"
    CMOS = "CMOS"
    DMOS = "DMOS"
    CSMOS = "CSMOS"
    CUSTOM_SINGLE = "CUSTOM_SINGLE"
    CUSTOM_DOUBLE = "CUSTOM_DOUBLE"

    # AI evaluation types
    ASR = "ASR"

    def get_type(self) -> str:
        if self.value in ["CUSTOM_SINGLE", "CUSTOM_DOUBLE"]:
            return "CUSTOM"
        elif self.value == "PREF":
            return "SPEECH_PREFERENCE"
        return f"SPEECH_{self.value}"

    @staticmethod
    def get_type_by_batch_size(batch_size: int) -> "EvalType":
        if batch_size == 1:
            return EvalType.CUSTOM_SINGLE
        elif batch_size == 2:
            return EvalType.CUSTOM_DOUBLE
        elif batch_size == 3:
            return EvalType.CSMOS
        else:
            raise ValueError(f"Invalid batch size: {batch_size}. Use one of the following: {', '.join([item.value for item in EvalType])}")

    @staticmethod
    def get_single_types() -> List["EvalType"]:
        """Get all single stimulus evaluation types"""
        return [EvalType.NMOS, EvalType.QMOS, EvalType.P808, EvalType.CUSTOM_SINGLE]

    @staticmethod
    def get_double_types() -> List["EvalType"]:
        """Get all double stimuli evaluation types"""
        return [EvalType.PREF, EvalType.SMOS, EvalType.CMOS, EvalType.CUSTOM_DOUBLE]

    @staticmethod
    def get_triple_types() -> List["EvalType"]:
        """Get all triple stimuli evaluation types"""
        return [EvalType.CSMOS]

    @staticmethod
    def is_single(type_str: str) -> bool:
        """Check if type is single stimulus"""
        return EvalType(type_str) in EvalType.get_single_types()

    @staticmethod
    def is_double(type_str: str) -> bool:
        """Check if type is double stimuli"""
        return EvalType(type_str) in EvalType.get_double_types()

    @staticmethod
    def is_triple(type_str: str) -> bool:
        """Check if type is triple stimuli"""
        return EvalType(type_str) in EvalType.get_triple_types()

    @staticmethod
    def is_eval_type(eval_type: str) -> bool:
        return any([item for item in EvalType if item.value == eval_type])


class AIEvalType(Enum):
    ASR = "ASR"
    ALL = "ALL"

    @classmethod
    def from_value(cls, value):
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"{value} is not a valid value for {cls.__name__}")

    @staticmethod
    def is_ai_type(eval_type: "AIEvalType") -> bool:
        return any([item for item in AIEvalType if item == eval_type])


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

    @staticmethod
    def is_score(usage_type: "QuestionUsageType") -> bool:
        return usage_type == QuestionUsageType.SCORE


class InstructionCategory(Enum):
    DO = "DO"
    WARNING = "WARNING"
    DONT = "DONT"


class QuestionRelatedModel(Enum):
    ALL = "ALL"
    MODEL_A = "MODEL_A"
    MODEL_B = "MODEL_B"

    @staticmethod
    def from_value(value: str) -> "QuestionRelatedModel":
        for member in QuestionRelatedModel:
            if member.value == value:
                return member
        raise ValueError(f"Invalid related model: {value}. Use one of the following: {', '.join([item.value for item in QuestionRelatedModel])}")

    @staticmethod
    def is_member(value: str) -> bool:
        return value in [item.value for item in QuestionRelatedModel]


class CollectionTarget(Enum):
    AUDIO = "AUDIO"

    @staticmethod
    def from_value(value: str) -> "CollectionTarget":
        for member in CollectionTarget:
            if member.value == value:
                return member
        raise ValueError(f"Invalid collection target: {value}. Use one of the following: {', '.join([item.value for item in CollectionTarget])}")


class CollectionCustomerStatus(Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SpeechStyle(str, Enum):
    NONE = "NONE"
    NARRATIVE = "NARRATIVE"
    CONVERSATION = "CONVERSATION"
    POEM = "POEM"
    STORY = "STORY"
    NEWS = "NEWS"
    ADVERTISEMENT = "ADVERTISEMENT"


class SpeechEmotion(str, Enum):
    NONE = "NONE"
    NEUTRAL = "NEUTRAL"
    HAPPY = "HAPPY"
    SAD = "SAD"
    ANGRY = "ANGRY"
    SURPRISED = "SURPRISED"
    DISGUSTED = "DISGUSTED"
    FEARFUL = "FEARFUL"
    EXCITED = "EXCITED"
    SARCASTIC = "SARCASTIC"
    ENCOURAGING = "ENCOURAGING"
    PLAYFUL = "PLAYFUL"
    SERIOUS = "SERIOUS"


class SpeechSpeed(str, Enum):
    SLOW = "SLOW"
    NORMAL = "NORMAL"
    FAST = "FAST"
