from dataclasses import dataclass

@dataclass
class StimulusStats:
    stimulus_name: str
    mean: float
    median: float
    std: float
    ci_90: float
    ci_95: float
    ci_99: float
    
    @staticmethod
    def from_dict(data: dict) -> 'StimulusStats':
        required_keys = ["stimulus_name", "mean", "median", "std", "ci_90", "ci_95", "ci_99"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Invalid data format for StimulusStatsResponseDto: {data}")
        
        return StimulusStats(
            stimulus_name=data['stimulus_name'],
            mean=data['mean'],
            median=data['median'],
            std=data['std'],
            ci_90=data['ci_90'],
            ci_95=data['ci_95'],
            ci_99=data['ci_99']
        )
    
    def to_dict(self) -> dict:
        return {
            "stimulus_name": self.stimulus_name,
            "mean": self.mean,
            "median": self.median,
            "std": self.std,
            "ci_90": self.ci_90,
            "ci_95": self.ci_95,
            "ci_99": self.ci_99
        }