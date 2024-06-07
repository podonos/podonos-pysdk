from typing import Optional

from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluator import Evaluator

class Client:
    """Podonos Client class. Used for creating individual evaluator."""

    _api_key: str
    _api_url: str
    _initialized: bool = False
    
    def __init__(self, api_key: str, api_url: str):
        self._api_key = api_key
        self._api_url = api_url
        self._initialized = True
    
    @property
    def api_key(self) -> str:
        return self._api_key
    
    @property
    def api_url(self) -> str:
        return self._api_url

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
            api_key=self._api_key, 
            api_url=self._api_url, 
            eval_config=EvalConfig(
                name=name,
                desc=desc,
                type=type,
                lan=lan,
                num_eval=num_eval,
                due_hours=due_hours
            ))