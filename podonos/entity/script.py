from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from podonos.common.enum import SpeechStyle, SpeechEmotion, SpeechSpeed


@dataclass
class ScriptEntity:
    id: str
    collection_id: str
    text: str
    estimated_duration: int
    required_count: int
    collected_count: int
    speech_style: SpeechStyle
    emotion: SpeechEmotion
    speed: SpeechSpeed
    meta_data: Dict
    created_time: datetime
    updated_time: datetime

    @staticmethod
    def from_dict(data: dict) -> "ScriptEntity":
        return ScriptEntity(
            id=data["id"],
            collection_id=data["collection_id"],
            text=data["text"],
            estimated_duration=data["estimated_duration"],
            required_count=data["required_count"],
            collected_count=data["collected_count"],
            speech_style=SpeechStyle(data["speech_style"]),
            emotion=SpeechEmotion(data["emotion"]),
            speed=SpeechSpeed(data["speed"]),
            meta_data=data["meta_data"],
            created_time=data["created_time"],
            updated_time=data["updated_time"],
        )
