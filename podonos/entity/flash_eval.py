from dataclasses import dataclass
from typing import Any, Dict, Optional

from podonos.core.file import File


@dataclass
class FlashEvalResult:
    naturalness: Optional[float]
    noise_quality: Optional[float]
    file: File
    id: Optional[str]
    message: Optional[str]

    @staticmethod
    def from_dict(data: Dict[str, Any], file: File, id: Optional[str] = None) -> "FlashEvalResult":
        raw_scores = data.get("scores")
        scores = raw_scores if isinstance(raw_scores, dict) else {}
        naturalness = scores.get("naturalness")
        noise_quality = scores.get("noise_quality")

        return FlashEvalResult(
            naturalness=naturalness,
            noise_quality=noise_quality,
            file=file,
            id=id,
            message=data.get("message"),
        )
