from dataclasses import dataclass
from typing import List


@dataclass
class StimulusStatsFile:
    name: str
    tags: List[str]
    
    @staticmethod
    def from_dict(data: dict) -> 'StimulusStatsFile':
        required_keys = ["name", "tags"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStatsFile: {data}")
        return StimulusStatsFile(
            name=data["name"],
            tags=data["tags"]
        )
        
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tags": self.tags
        }
    
@dataclass
class StimulusStats:
    files: List[StimulusStatsFile]
    mean: float
    median: float
    std: float
    ci_90: float
    ci_95: float
    ci_99: float
    
    @staticmethod
    def from_dict(data: dict) -> 'StimulusStats':
        required_keys = ["files", "mean", "median", "std", "ci_90", "ci_95", "ci_99"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStats: {data}")
        
        files = [StimulusStatsFile.from_dict(file) for file in data["files"]]
        return StimulusStats(
            files=files,
            mean=data['mean'],
            median=data['median'],
            std=data['std'],
            ci_90=data['ci_90'],
            ci_95=data['ci_95'],
            ci_99=data['ci_99']
        )
    
    def to_dict(self) -> dict:
        return {
            "files": [file.to_dict() for file in self.files],
            "mean": self.mean,
            "median": self.median,
            "std": self.std,
            "ci_90": self.ci_90,
            "ci_95": self.ci_95,
            "ci_99": self.ci_99
        }