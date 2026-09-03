from dataclasses import dataclass
from typing import Optional, Any, Dict
from datetime import datetime, timezone


def _parse_time(value: str) -> datetime:
    """Parse a server timestamp into an aware UTC datetime.

    The backend sends one clock but two spellings: created_time carries a trailing "Z",
    started_time may carry no offset at all. Without normalizing, one parses aware and the
    other naive, and subtracting them raises TypeError.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_optional_time(value: Optional[str]) -> Optional[datetime]:
    """Parse a timestamp the server may send as null, degrading to None on a bad value.

    started_time and ended_time are genuinely null on a DRAFT evaluation. They are also
    optional, so one malformed value must not take the whole evaluation list down with it
    the way a bad required field would.
    """
    if value is None:
        return None
    try:
        return _parse_time(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _format_time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _format_optional_time(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else _format_time(value)


@dataclass
class EvaluationEntity:
    id: str
    title: str
    internal_name: Optional[str]
    description: Optional[str]
    batch_size: int
    status: str
    created_time: datetime
    updated_time: datetime
    # Progress fields. Optional because only the workspace evaluation list and the create
    # responses carry them; anything else parsed into this entity would otherwise break.
    progress: Optional[float] = None
    internal_status: Optional[str] = None
    started_time: Optional[datetime] = None
    ended_time: Optional[datetime] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "EvaluationEntity":
        required_keys = ["id", "title", "batch_size", "status", "created_time", "updated_time"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for Evaluation: {data}")

        return EvaluationEntity(
            id=data["id"],
            title=data["title"],
            internal_name=data["internal_name"],
            description=data["description"],
            batch_size=data["batch_size"],
            status=data["status"],
            created_time=_parse_time(data["created_time"]),
            updated_time=_parse_time(data["updated_time"]),
            progress=data.get("progress"),
            internal_status=data.get("internal_status"),
            started_time=_parse_optional_time(data.get("started_time")),
            ended_time=_parse_optional_time(data.get("ended_time")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "internal_name": self.internal_name,
            "description": self.description,
            "batch_size": self.batch_size,
            "status": self.status,
            "progress": self.progress,
            "internal_status": self.internal_status,
            "started_time": _format_optional_time(self.started_time),
            "ended_time": _format_optional_time(self.ended_time),
            "created_time": _format_time(self.created_time),
            "updated_time": _format_time(self.updated_time),
        }


@dataclass
class EvaluationProgress:
    """One evaluation's progress, as returned by GET evaluations/{id}/progress.

    Deliberately not an EvaluationEntity. That entity requires title, batch_size,
    created_time and updated_time, none of which this endpoint returns, so parsing the
    progress payload into it raises. See ``Client.get_evaluation_progress`` for how to
    read these fields.
    """

    id: str
    status: str
    internal_status: str
    progress: float
    started_time: Optional[datetime] = None
    ended_time: Optional[datetime] = None

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "EvaluationProgress":
        required_keys = ["id", "status", "internal_status", "progress"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for EvaluationProgress: {data}")

        return EvaluationProgress(
            id=data["id"],
            status=data["status"],
            internal_status=data["internal_status"],
            progress=data["progress"],
            started_time=_parse_optional_time(data.get("started_time")),
            ended_time=_parse_optional_time(data.get("ended_time")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "internal_status": self.internal_status,
            "progress": self.progress,
            "started_time": _format_optional_time(self.started_time),
            "ended_time": _format_optional_time(self.ended_time),
        }
