import csv
import os
import requests
from requests import Response
from typing import Any, Dict, List, Literal, Optional

from podonos.common.exception import HTTPError
from podonos.common.util import get_content_type_by_filename
from podonos.core.base import log
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.file import Audio, AudioGroup
from podonos.core.stimulus_stats import StimulusStats
from podonos.entity.evaluation import EvaluationEntity


class EvaluationService:
    """Service class for handling evaluation-related API communications"""

    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    def create(self, config: EvalConfig) -> EvaluationEntity:
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
            evaluation = EvaluationEntity.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def create_from_template(self, config: EvalConfig) -> EvaluationEntity:
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
            evaluation = EvaluationEntity.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    def get_evaluation(self, evaluation_id: str) -> EvaluationEntity:
        """Get evaluation by ID"""
        try:
            response = self.api_client.get(f"evaluations/{evaluation_id}")
            response.raise_for_status()
            return EvaluationEntity.from_dict(response.json())
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation: {e}")

    def get_evaluation_list(self) -> List[Dict[str, Any]]:
        """Gets a list of evaluations.

        Args: None

        Returns:
            Evaluation containing all the evaluation info
        """
        try:
            response = self.api_client.get("evaluations")
            response.raise_for_status()
            evaluations = [EvaluationEntity.from_dict(evaluation) for evaluation in response.json()]
            return [evaluation.to_dict() for evaluation in evaluations]
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation list: {e}")

    def get_stats_dict_by_id(self, evaluation_id: str, group_by: Literal["question", "script", "model"] = "question") -> List[Dict[str, Any]]:
        """Gets a list of evaluation statistics referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            group_by: Group by question or script. Default: "question". "script" is only available for single-question evaluation.

        Returns:
            List of statistics for the evaluation.
        """
        try:
            response = self.api_client.get(f"evaluations/{evaluation_id}/stats?group-by={group_by}")
            if response.status_code == 400:
                log.info(f"Bad Request: The {evaluation_id} is an invalid evaluation id")
                return []

            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise HTTPError(f"Failed to get evaluation stats: {e}")

    def download_stats_csv_by_id(self, evaluation_id: str, output_path: str) -> None:
        """Downloads the evaluation statistics into CSV referenced by id.

        Args:
            evaluation_id: Evaluation id. See get_evaluation_list() above.
            output_path: Path to the output CSV.

        Returns: None
        """
        log.check_ne(evaluation_id, "")
        log.check_ne(output_path, "")

        # Fetch stats using the existing method
        stats = self.get_stats_dict_by_id(evaluation_id)

        # Open the output file for writing
        with open(output_path, "w", newline='') as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            header = [
                "question", "description", "order", "name", "tags", "type", "script", "model_tag",
                "mean", "median", "std", "sem", "ci_95", "other_options"
            ]
            writer.writerow(header)

            # Process each item in stats
            for item in stats:
                question = item.get("question")
                description = item.get("description")
                order = item.get("order")

                for response in item.get("responses", []):
                    # Check if 'targets' key exists
                    if "targets" in response:
                        for target in response["targets"]:
                            row = [
                                question,
                                description,
                                order,
                                target.get("name"),
                                ", ".join(target.get("tags", [])),
                                target.get("type"),
                                target.get("script"),
                                target.get("model_tag"),
                                response.get("mean"),
                                response.get("median"),
                                response.get("std"),
                                response.get("sem"),
                                response.get("ci_95"),
                                {k: v for k, v in response.items() if k not in ["targets", "mean", "median", "std", "sem", "ci_95"]}
                            ]
                            writer.writerow(row)
                    else:
                        # Handle single target format
                        row = [
                            question,
                            description,
                            order,
                            response.get("name"),
                            ", ".join(response.get("tags", [])),
                            response.get("type"),
                            response.get("script"),
                            response.get("model_tag"),
                            response.get("mean"),
                            response.get("median"),
                            response.get("std"),
                            response.get("sem"),
                            response.get("ci_95"),
                            {k: v for k, v in response.items() if k not in ["name", "tags", "type", "script", "model_tag", "mean", "median", "std", "sem", "ci_95"]}
                        ]
                        writer.writerow(row)

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
