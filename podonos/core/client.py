from typing import Any, Dict, Optional, List

from requests import HTTPError

from podonos.core.api import APIClient
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluation import EvaluationInformation
from podonos.core.evaluator import Evaluator
from podonos.core.stimulus_stats import StimulusStats

class Client:
    """Podonos Client class. Used for creating individual evaluator and managing the evaluations."""

    _api_client: APIClient
    _initialized: bool = False
    
    def __init__(self, api_client: APIClient):
        self._api_client = api_client
        self._initialized = True

    def create_evaluator(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalConfigDefault.TYPE.value,
        lan: str = EvalConfigDefault.LAN.value,
        granularity: float = EvalConfigDefault.GRANULARITY,
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS,
        auto_start: bool = EvalConfigDefault.AUTO_START
    ) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://docs.dyspatch.io/localization/supported_languages/

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. One of {'NMOS', 'SMOS', 'P808'}. Default: NMOS
            lan: Human language for this audio. One of those in Language. Default: en-us
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 3.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.
            auto_start: The evaluation start automatically if True. Manually start in the workspace otherwise.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        # TODO: fix this clearly
        if type not in "SPEECH_":
            type = "SPEECH_" + type

        return Evaluator(
            api_client=self._api_client,
            eval_config=EvalConfig(
                name=name,
                desc=desc,
                type=type,
                lan=lan,
                granularity=granularity,
                num_eval=num_eval,
                due_hours=due_hours,
                auto_start=auto_start
            ))
    
    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Args: None

        Returns:
            EvaluationInformation containing all the evaluation info
        """
        try:
            response = self._api_client.get("evaluations")
            response.raise_for_status()
            evaluations = [EvaluationInformation.from_dict(evaluation) for evaluation in response.json()]
            return [evaluation.to_dict() for evaluation in evaluations]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation list: {e}")
    
    def get_stimulus_stats_by_id(self, evaluation_id: str) -> List[Dict[str, Any]]:
        """Gets evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id.

        Returns:
            StimulusStats containing all evaluation statistics.
        """
        try:
            response = self._api_client.get(f"evaluations/{evaluation_id}/stats")
            response.raise_for_status()
            stats = [StimulusStats.from_dict(stats) for stats in response.json()]
            return [stat.to_dict() for stat in stats]
        except Exception as e:
            raise HTTPError(f"Failed to get stimulus stats: {e}")
    
    def download_stimulus_stats_csv_by_id(self, evaluation_id: str, output_path: str) -> None:
        """Downloads the evaluation statistics into CSV referenced by id.

        Args:
            evaluation_id: Evaluation id
            output_path: Path to the output CSV

        Returns: None
        """
        stats = self.get_stimulus_stats_by_id(evaluation_id)
        with open(output_path, "w") as f:
            f.write("stimulus_name,mean,median,std,ci_90,ci_95,ci_99\n")
            for stat in stats:
                f.write(f"{stat['stimulus_name']},{stat['mean']},{stat['median']},{stat['std']},{stat['ci_90']},{stat['ci_95']},{stat['ci_99']}\n")