from typing import Optional

from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.evaluator import Evaluator

from podonos.common.constant import PODONOS_CONTACT_EMAIL
from podonos.common.enum import AIEvalType, EvalType
from podonos.service.ai_evaluation_service import AIEvaluationService


class AIEvaluation:
    _api_client: APIClient
    _ai_evaluation_service: AIEvaluationService

    def __init__(self, api_client: APIClient):
        self._api_client = api_client
        self._ai_evaluation_service = AIEvaluationService(api_client)

    def create(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        type: str = EvalType.CUSTOM_SINGLE.value,
        lan: str = EvalConfigDefault.LAN.value,
        ai_type: AIEvalType = AIEvalType.ALL,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """
        Create an AI evaluator. For getting ASR results, file's script must be provided.

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            type: Only ASR is supported. Default: ASR
            lan: Human language for this audio. One of those in Language. Default: en-us
            ai_type: AI type. Default: ASR
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
        """
        if not AIEvalType.is_ai_type(ai_type):
            raise ValueError(f'"type" must be one of {{ALL}}. \n' + f"Do you want other evaluation types? Let us know at {PODONOS_CONTACT_EMAIL}")

        evaluator = Evaluator(
            self._api_client,
            EvalConfig(name=name, desc=desc, type=type, lan=lan, max_upload_workers=max_upload_workers, ai_type=ai_type),
            [EvalType(type)],
        )
        if ai_type == AIEvalType.ALL:
            log.info(f"Creating AI evaluation for {evaluator.get_evaluation_id()} with {AIEvalType.ALL}")
            self._ai_evaluation_service.create(evaluator.get_evaluation_id(), AIEvalType.ALL)
        return evaluator

    def asr(
        self,
        name: Optional[str] = None,
        desc: Optional[str] = None,
        lan: str = EvalConfigDefault.LAN.value,
        max_upload_workers: int = EvalConfigDefault.MAX_UPLOAD_WORKERS,
    ) -> Evaluator:
        """
        Create an ASR evaluator. file's script must be provided.

        Args:
            name: This session name. Its length must be > 1. If empty, a random name is used. Optional.
            desc: Description of this session. Optional.
            lan: Human language for this audio. One of those in Language. Default: en-us
            max_upload_workers: The maximum number of upload workers. Must be a positive integer. Default: 20
        """
        return self.create(name, desc, EvalType.CUSTOM_SINGLE.value, lan, AIEvalType.ASR, max_upload_workers)
