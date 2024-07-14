from typing import Any, Dict, Optional, List

from requests import HTTPError

from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluation import Evaluation
from podonos.core.evaluator import Evaluator
from podonos.core.stimulus_stats import StimulusStats
from podonos.evaluators.double_stimuli_evaluator import DoubleStimuliEvaluator
from podonos.evaluators.single_stimulus_evaluator import SingleStimulusEvaluator

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
        
        if not EvalType.is_eval_type(type):
            raise ValueError("Not supported evaluation types. 'NMOS', 'QMOS', 'P808', 'SMOS' are allowed to do")
        
        eval_config = EvalConfig(
            name=name, desc=desc,
            type=type, lan=lan,
            granularity=granularity, num_eval=num_eval,
            due_hours=due_hours, auto_start=auto_start
        )
        if type in [EvalType.SMOS.value]:
            return DoubleStimuliEvaluator(
                supported_evaluation_type=[EvalType.SMOS],
                api_client=self._api_client,
                eval_config=eval_config
            )
        
        return SingleStimulusEvaluator(
            supported_evaluation_type=[EvalType.NMOS, EvalType.QMOS, EvalType.P808],
            api_client=self._api_client,
            eval_config=eval_config
        )
    
    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Args: None

        Returns:
            EvaluationInformation containing all the evaluation info
        """
        try:
            response = self._api_client.get("evaluations")
            response.raise_for_status()
            evaluations = [Evaluation.from_dict(evaluation) for evaluation in response.json()]
            return [evaluation.to_dict() for evaluation in evaluations]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation list: {e}")
    
    def get_stats_dict_by_id(self, evaluation_id: str) -> List[Dict[str, Any]]:
        """Gets a list of evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.

        Returns:
            List of statistics for the evaluation.
        """
        try:
            response = self._api_client.get(f"evaluations/{evaluation_id}/stats")
            response.raise_for_status()
            stats = [StimulusStats.from_dict(stats) for stats in response.json()]
            return [stat.to_dict() for stat in stats]
        except Exception as e:
            raise HTTPError(f"Failed to get stimulus stats: {e}")
    
    def download_stats_csv_by_id(self, evaluation_id: str, output_path: str) -> None:
        """Downloads the evaluation statistics into CSV referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            output_path: Path to the output CSV.

        Returns: None
        """
        stats = self.get_stats_dict_by_id(evaluation_id)
        with open(output_path, "w") as f:
            f.write("stimulus_name,mean,median,std,ci_90,ci_95,ci_99\n")
            for stat in stats:
                f.write(f"{stat['stimulus_name']},{stat['mean']},{stat['median']},{stat['std']},{stat['ci_90']},{stat['ci_95']},{stat['ci_99']}\n")