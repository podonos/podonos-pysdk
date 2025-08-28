import json
import os
from requests import Response
from typing import Any, Dict, List, Literal, Optional
import hashlib
from tqdm import tqdm

from podonos.common.constant import CONTENT_TYPE_TO_EXTENSION
from podonos.common.exception import HTTPError
from podonos.common.util import get_content_type_by_filename
from podonos.core.base import log
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.file import Audio, AudioGroup
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

    def get_stats_json_by_id(self, evaluation_id: str, group_by: Literal["question", "script", "model"] = "question") -> List[Dict[str, Any]]:
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

    def create_evaluation_files(self, evaluation_id: str, audios: List[Audio]):
        try:
            response = self.api_client.put(
                f"evaluations/{evaluation_id}/files",
                {"files": [audio.to_create_file_dict() for audio in audios]},
            )
            response.raise_for_status()
        except Exception as e:
            log.error(f"HTTP error in adding file meta: {e}")
            raise HTTPError(
                f"Failed to create evaluation files: {e}",
                status_code=getattr(e, 'response', {}).get('status_code') if hasattr(e, 'response') else None,
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
            with open(path, "rb") as file:
                response = self.api_client.external_put(
                    url,
                    data=file,
                    headers={"Content-Type": get_content_type_by_filename(path)},
                )
            return response
        except Exception as e:
            log.error(f"HTTP error in uploading a file to presigned URL: {e}")
            raise HTTPError(
                f"Failed to Upload File {path}: {e}",
                status_code=getattr(e, 'response', {}).get('status_code') if hasattr(e, 'response') else None,
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
            for key, value in headers.items():
                log.debug(f"{key}: {value}")

        try:
            response = self.api_client.external_put(url, json_data=data, headers=headers)
            return response
        except Exception as e:
            log.error(f"HTTP error in uploading a json to presigned url: {e}")
            raise HTTPError(
                f"Failed to Upload JSON {data}: {e}",
                status_code=getattr(e, 'response', {}).get('status_code') if hasattr(e, 'response') else None,
            )

    def download_evaluation_files_by_evaluation_id(self, evaluation_id: str, output_dir: str) -> str:
        """Download evaluation files using CloudFront cookies."""
        try:
            # Get the response from the API
            log.debug(f"Download evaluation files for evaluation {evaluation_id}")
            file_mata_json = {"files": []}
            response = self.api_client.get(f"evaluation-files/download?evaluation-id={evaluation_id}")
            response.raise_for_status()

            # Parse the response using EvaluationFileDownloadResponseDto
            download_response = response.json()

            # Ensure the output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Download each file using the original URL and cookies
            for file in tqdm(download_response["files"], desc="Downloading files", unit="file"):
                # Download the file using the original URL and cookies
                file_response = self.api_client.external_get(
                    file["original_url"], 
                    cookies=download_response["cookie"]
                )
                file_response.raise_for_status()

                content_type = file_response.headers.get("Content-Type")
                file_extension = CONTENT_TYPE_TO_EXTENSION[content_type] if content_type else ".flac"

                # Generate a hash for the original file name
                file_original_name = file["original_name"]
                hash_object = hashlib.md5(file_original_name.encode())
                hashed_file_name = hash_object.hexdigest()

                # Construct the file path using the model tag and hashed file name
                file_name = f"{file['model_tag']}/{hashed_file_name}{file_extension}"
                file_path = os.path.join(output_dir, file_name)

                # Ensure the directory for the model tag exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                # Save the file locally
                with open(file_path, "wb") as f:
                    f.write(file_response.content)

                file_mata_json["files"].append(
                    {
                        "file_path": file_path,
                        "original_name": file_original_name,
                        "model_tag": file["model_tag"],
                        "tags": file["tags"],
                    }
                )

            log.info(f"Downloaded {len(file_mata_json['files'])} files")

            # Save the file metadata to a JSON file
            metadata_file_path = os.path.join(output_dir, "metadata.json")
            with open(metadata_file_path, "w") as f:
                json.dump(file_mata_json, f)
            log.info(f"File metadata saved to {metadata_file_path}")

            return "Files downloaded successfully."
        except Exception as e:
            raise HTTPError(f"Failed to download evaluation files: {e}")
