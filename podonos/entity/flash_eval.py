from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FlashFileInfo:
    filename: str
    filetype: str
    mimetype: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "FlashFileInfo":
        return FlashFileInfo(
            filename=data.get("filename", ""),
            filetype=data.get("filetype", ""),
            mimetype=data.get("mimetype", ""),
        )


@dataclass
class FlashEvalResult:
    naturalness: Optional[float]
    files: List[FlashFileInfo]
    message: Optional[str]

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "FlashEvalResult":
        scores = data.get("scores", {})
        naturalness = scores.get("naturalness") if isinstance(scores, dict) else None

        files_data = data.get("files", [])
        files = [FlashFileInfo.from_dict(f) for f in files_data]

        return FlashEvalResult(
            naturalness=naturalness,
            files=files,
            message=data.get("message"),
        )
