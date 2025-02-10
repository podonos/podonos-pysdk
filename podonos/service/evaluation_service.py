import os
import requests
from requests import Response
from typing import Any, Dict, List, Optional

from podonos.common.util import get_content_type_by_filename
from podonos.core.audio import Audio, AudioGroup
from podonos.core.base import log
from podonos.core.api import APIClient
from podonos.core.evaluation import Evaluation
from podonos.core.config import EvalConfig
from podonos.common.exception import HTTPError


class EvaluationService:
    """Service class for handling evaluation-related API communications"""

    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    def create(self, config: EvalConfig) -> Evaluation:
        """
        Create a new evaluation based on the evaluation configuration

        Raises:
            HTTPError: If the value is invalid

        Returns:
            Evaluation: Get new evaluation information
        """
        log.debug("Create evaluation")
        try:
            response = self.api_client.post("evaluations", data=config.to_create_request_dto())
            response.raise_for_status()
            evaluation = Evaluation.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def create_from_template(self, config: EvalConfig) -> Evaluation:
        """
        Create a new evaluation based on built-in template

        Raises:
            HTTPError: If the template id is invalid

        Returns:
            Evaluation: Get new evaluation information
        """
        log.debug("Create Evaluation from Template")
        try:
            response = self.api_client.post("evaluations/templates", data=config.to_create_from_template_request_dto())
            response.raise_for_status()
            evaluation = Evaluation.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def get_evaluation(self, evaluation_id: str) -> Evaluation:
        """Get evaluation by ID"""
        try:
            response = self.api_client.get(f"evaluations/{evaluation_id}")
            response.raise_for_status()
            return Evaluation.from_dict(response.json())
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation: {e}")

    def create_evaluation_files(self, evaluation_id: str, audios: List[Audio]):
        try:
            response = self.api_client.put(
                f"evaluations/{evaluation_id}/files",
                {"files": [audio.to_create_file_dict() for audio in audios]},
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP error in adding file meta: {e}")
            raise HTTPError(
                f"Failed to create evaluation files: {e}",
                status_code=e.response.status_code if e.response else None,
            )

    def get_presigned_url(self, evaluation_id: str, remote_object_name: str) -> str:
        """Get presigned URL for file upload"""
        try:
            response = self.api_client.put(
                f"evaluations/{evaluation_id}/uploading-presigned-url",
                data={"uploaded_file_name": remote_object_name},
            )
            response.raise_for_status()
            return response.text.replace('"', "")
        except Exception as e:
            log.error(f"HTTP error in getting a presigned url: {e}")
            raise HTTPError(f"Failed to get presigned URL: {e}")

    def upload_evaluation_file(self, url: str, path: str) -> Response:
        log.check_notnone(url)
        log.check_notnone(path)
        log.check_ne(url, "")
        log.check_ne(path, "")
        log.check(os.path.isfile(path), f"{path} doesn't exist")
        log.check(os.access(path, os.R_OK), f"{path} isn't readable")

        try:
            response = requests.put(
                url,
                data=open(path, "rb"),
                headers={"Content-Type": get_content_type_by_filename(path)},
            )
            return response
        except requests.exceptions.RequestException as e:
            log.error(f"HTTP error in uploading a file to presigned URL: {e}")
            raise HTTPError(
                f"Failed to Upload File {path}: {e}",
                status_code=e.response.status_code if e.response else None,
            )

    def upload_session_json(self, evaluation_id: str, config: EvalConfig, audio_groups: List[AudioGroup]) -> None:
        """Upload session JSON data"""
        try:
            session_json = config.to_dict()
            session_json["files"] = [group.to_dict() for group in audio_groups]
            presigned_url = self.get_presigned_url(evaluation_id, "session.json")
            self.put_session_json(presigned_url, session_json, headers={"Content-type": "application/json"})
        except Exception as e:
            raise HTTPError(f"Failed to upload session JSON: {e}")

    def put_session_json(self, url: str, data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Response:
        log.check_notnone(url)
        log.check_ne(url, "")

        log.debug("JSON data")
        for key, value in data.items():
            log.debug(f"{key}: {value}")
        if headers:
            log.debug("Headers")
            for key, value in data.items():
                log.debug(f"{key}: {value}")

        try:
            response = requests.put(url, json=data, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            log.error(f"HTTP error in uploading a json to presigned url: {e}")
            raise HTTPError(
                f"Failed to Upload JSON {data}: {e}",
                status_code=e.response.status_code if e.response else None,
            )
