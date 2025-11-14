from podonos.common.enum import AIEvalType
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.common.validator import Rules, validate_args


class AIEvaluationService:
    def __init__(self, api_client: APIClient) -> None:
        self.api_client = api_client

    @validate_args(evaluation_id=Rules.uuid_not_none, ai_eval_type=Rules.instance_of(AIEvalType))
    def create(self, evaluation_id: str, ai_eval_type: AIEvalType) -> None:
        try:
            log.debug(f"Creating AI evaluation for {evaluation_id} with {ai_eval_type}")
            response = self.api_client.post("ai-evaluation-requests", data={"evaluation_id": evaluation_id, "type": ai_eval_type.value})
            response.raise_for_status()
        except Exception as e:
            log.error(f"Error creating AI evaluation for {evaluation_id} with {ai_eval_type}: {e}")
            raise e
