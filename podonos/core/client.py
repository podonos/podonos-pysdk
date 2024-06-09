from typing import Optional, List

from requests import HTTPError

from podonos.core.api import APIClient
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluation import EvaluationInformation
from podonos.core.evaluator import Evaluator
from podonos.core.stimulus_stats import StimulusStats

class Client:
    """Podonos Client class. Used for creating individual evaluator."""

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
        num_eval: int = EvalConfigDefault.NUM_EVAL,
        due_hours: int = EvalConfigDefault.DUE_HOURS
    ) -> Evaluator:
        """Creates a new evaluator with a unique evaluation session ID.
        For the language code, see https://docs.dyspatch.io/localization/supported_languages/

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Evaluation type. One of {'NMOS', 'SMOS', 'P808'}. Default: NMOS
            lan: Human language for this audio. One of {'en-us', 'ko-kr', 'audio'}. Default: en-us
            num_eval: The minimum number of repetition for each audio evaluation. Should be >=1. Default: 3.
            due_hours: An expected number of days of finishing this mission and getting the evaluation report.
                        Must be >= 12. Default: 12.

        Returns:
            Evaluator instance.

        Raises:
            ValueError: if this function is called before calling init().
        """

        if not self._initialized:
            raise ValueError("This function is called before initialization.")

        return Evaluator(
            api_client=self._api_client,
            eval_config=EvalConfig(
                name=name,
                desc=desc,
                type=type,
                lan=lan,
                num_eval=num_eval,
                due_hours=due_hours
            ))
    
    def get_evaluation_list(self) -> List[EvaluationInformation]:
        try:
            response = self._api_client.get("evaluations")
            response.raise_for_status()
            return [EvaluationInformation(**evaluation) for evaluation in response.json()]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation list: {e}")
    
    def get_stimulus_stats_by_id(self, evaluation_id: str) -> List[StimulusStats]:
        try:
            response = self._api_client.get(f"evaluations/{evaluation_id}/stats")
            response.raise_for_status()
            return [StimulusStats.from_dict(**stats) for stats in response.json()]
        except Exception as e:
            raise HTTPError(f"Failed to get stimulus stats: {e}")