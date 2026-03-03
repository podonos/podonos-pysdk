from dataclasses import dataclass
from typing import Any, Dict, Optional

from podonos.core.file import File


@dataclass
class FlashEvalResult:
    naturalness: Optional[float]
    file: File
    eval_id: Optional[str]
    message: Optional[str]

    @staticmethod
    def from_dict(data: Dict[str, Any], file: File, eval_id: Optional[str] = None) -> "FlashEvalResult":
        scores = data.get("scores", {})
        naturalness = scores.get("naturalness") if isinstance(scores, dict) else None

        return FlashEvalResult(
            naturalness=naturalness,
            file=file,
            eval_id=eval_id,
            message=data.get("message"),
        )
