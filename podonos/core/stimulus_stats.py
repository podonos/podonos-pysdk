from dataclasses import dataclass, field
from typing import List, Union, Literal, Optional, Dict, Any


@dataclass
class StimulusStatsFile:
    name: str
    model_tag: str
    tags: List[str]
    type: Union[Literal["A"], Literal["B"]]

    @staticmethod
    def from_dict(data: dict) -> "StimulusStatsFile":
        required_keys = ["name", "model_tag", "tags", "type"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStatsFile: {data}")
        return StimulusStatsFile(name=data["name"], model_tag=data["model_tag"], tags=data["tags"], type=data["type"])

    def to_dict(self) -> dict:
        return {"name": self.name, "model_tag": self.model_tag, "tags": self.tags, "type": self.type}


@dataclass
class StimulusStatsQuestion:
    title: str
    order: int

    @staticmethod
    def from_dict(data: dict) -> "StimulusStatsQuestion":
        required_keys = ["title", "order"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStatsQuestion: {data}")
        return StimulusStatsQuestion(title=data["title"], order=data["order"])

    def to_dict(self) -> dict:
        return {"title": self.title, "order": self.order}


@dataclass
class StimulusStats:
    files: List[StimulusStatsFile]
    question: StimulusStatsQuestion
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    sem: Optional[float] = None
    ci_95: Optional[float] = None
    options: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict) -> "StimulusStats":
        required_keys = ["files", "question"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStats: {data}")

        files = [StimulusStatsFile.from_dict(file) for file in data["files"]]
        question = StimulusStatsQuestion.from_dict(data["question"])
        stats = StimulusStats(
            files=files,
            question=question,
        )

        optional_fields = ["mean", "median", "std", "sem", "ci_95"]
        for field in optional_fields:
            if field in data:
                setattr(stats, field, data[field])

        extra_fields = {k: v for k, v in data.items() if k not in required_keys + optional_fields}
        if extra_fields:
            stats.options.update(extra_fields)

        return stats

    def to_dict(self) -> dict:
        result = {
            "question": self.question.to_dict(),
            "files": [file.to_dict() for file in self.files],
        }

        optional_fields = ["mean", "median", "std", "sem", "ci_95"]
        for field in optional_fields:
            value = getattr(self, field)
            if value is not None:
                result[field] = value

        if self.options:
            result.update({"options": self.options})

        return result
