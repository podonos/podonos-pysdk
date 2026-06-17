import hashlib
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

from requests import Response
from tqdm import tqdm

from podonos.common.constant import CONTENT_TYPE_TO_EXTENSION
from podonos.common.exception import HTTPError
from podonos.common.redaction import redact_secrets
from podonos.common.util import get_content_type_by_filename
from podonos.common.validator import Rules, validate_args
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.core.file import Audio, AudioGroup
from podonos.entity.evaluation import EvaluationEntity
from podonos.entity.verification import ProcessFilesResponse, VerifyFilesResponse


_TRUTHY = {"1", "true", "yes", "y", "on"}
_PODONOS_DOWNLOAD_HOST_SUFFIXES = (".podonos.com", ".podonosapi.com")
_PODONOS_DOWNLOAD_EXACT_HOSTS = {"podonos.com", "podonosapi.com"}


class EvaluationService:
    """Service class for handling evaluation-related API communications"""

    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    @validate_args(evaluation_id=Rules.uuid_not_none, payload=Rules.dict_not_none)
    def update_specific_fields(
        self,
        evaluation_id: str,
        payload: Dict[str, Any],
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Patch specific fields of an evaluation (e.g., batch_size) without recreating it.
        Intended for late adjustments like updating RANKING batch_size.
        """
        try:
            endpoint = f"evaluations/{evaluation_id}/specific-fields"
            kwargs: Dict[str, Any] = {"data": payload}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if context is not None:
                request_context = dict(context)
                request_context["endpoint"] = endpoint
                request_context["evaluation_id"] = evaluation_id
                kwargs["context"] = request_context
            response = self.api_client.patch(endpoint, **kwargs)
            response.raise_for_status()
        except Exception as e:
            raise HTTPError(
                f"Failed to update evaluation specific fields: {e}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

    @validate_args(config=Rules.instance_of(EvalConfig))
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
            response = self.api_client.post(
                "evaluations",
                data=config.to_create_request_dto(),
                timeout=config.api_timeout,
                context={"endpoint": "evaluations"},
            )
            response.raise_for_status()
            evaluation = EvaluationEntity.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    @validate_args(config=Rules.instance_of(EvalConfig))
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
            response = self.api_client.post(
                "evaluations/templates",
                data=config.to_create_from_template_request_dto(),
                timeout=config.api_timeout,
                context={"endpoint": "evaluations/templates"},
            )
            response.raise_for_status()
            evaluation = EvaluationEntity.from_dict(response.json())
            log.info(f"Evaluation is generated: {evaluation.id}")
            return evaluation
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def get_evaluation(
        self,
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> EvaluationEntity:
        """Get evaluation by ID"""
        try:
            endpoint = f"evaluations/{evaluation_id}"
            kwargs: Dict[str, Any] = {}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if context is not None:
                request_context = dict(context)
                request_context["endpoint"] = endpoint
                request_context["evaluation_id"] = evaluation_id
                kwargs["context"] = request_context
            response = self.api_client.get(endpoint, **kwargs)
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

    @validate_args(evaluation_id=Rules.uuid_not_none, group_by=Rules.str_not_none)
    def get_stats_json_by_id(
        self,
        evaluation_id: str,
        group_by: Literal["question", "script", "model"] = "question",
    ) -> List[Dict[str, Any]]:
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

    @validate_args(evaluation_id=Rules.uuid_not_none, audios=Rules.list_not_none)
    def create_evaluation_files(
        self,
        evaluation_id: str,
        audios: List[Audio],
        timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
        idempotency_keys: Optional[List[str]] = None,
    ):
        try:
            endpoint = f"evaluations/{evaluation_id}/files"
            response = self.api_client.put(
                endpoint,
                {"files": self._build_create_files_body(audios, idempotency_keys)},
                timeout=timeout,
                context={
                    "endpoint": endpoint,
                    "evaluation_id": evaluation_id,
                    "file_count": len(audios),
                    **(context or {}),
                },
            )
            response.raise_for_status()
        except Exception as e:
            log.error(f"HTTP error in adding file meta: {e}")
            raise HTTPError(
                f"Failed to create evaluation files: {e}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

    @staticmethod
    def _build_create_files_body(
        audios: List[Audio], idempotency_keys: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """Build the create_evaluation_files request body (c3, shape b).

        When idempotency_keys is provided, a per-row `idempotency_key` is zipped into
        each file dict so the backend can collapse a retried/lost-response POST. The
        same `data` dict is reused across the HTTP-transport retry in
        ``api._execute_with_retry`` (the closure captures one body), so the key is
        byte-stable across retries for free. When None (e.g. callers that do not
        compute keys), the body is built exactly as before.
        """
        if idempotency_keys is None:
            return [audio.to_create_file_dict() for audio in audios]
        if len(idempotency_keys) != len(audios):
            raise ValueError(
                "idempotency_keys length must equal audios length "
                f"({len(idempotency_keys)} != {len(audios)})"
            )
        return [
            {**audio.to_create_file_dict(), "idempotency_key": key}
            for audio, key in zip(audios, idempotency_keys)
        ]

    @validate_args(evaluation_id=Rules.uuid_not_none, remote_object_name=Rules.str_not_none)
    def get_presigned_url(
        self,
        evaluation_id: str,
        remote_object_name: str,
        timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get presigned URL for file upload"""
        try:
            endpoint = f"evaluations/{evaluation_id}/uploading-presigned-url"
            response = self.api_client.put(
                endpoint,
                data={"uploaded_file_name": remote_object_name},
                timeout=timeout,
                context={
                    "endpoint": endpoint,
                    "evaluation_id": evaluation_id,
                    "file_count": 1,
                    **(context or {}),
                },
            )
            response.raise_for_status()
            return response.text.replace('"', "")
        except Exception as e:
            log.error(
                f"HTTP error in getting a presigned url: {redact_secrets(e)}"
            )
            raise HTTPError(f"Failed to get presigned URL: {redact_secrets(e)}")

    @validate_args(url=Rules.str_not_none, path=Rules.file_path_not_none)
    def upload_evaluation_file(
        self,
        url: str,
        path: str,
        timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        try:
            with open(path, "rb") as file:
                response = self.api_client.external_put(
                    url,
                    data=file,
                    headers={"Content-Type": get_content_type_by_filename(path)},
                    timeout=timeout,
                    context={
                        "file_count": 1,
                        **(context or {}),
                    },
                )
            response.raise_for_status()
            return response
        except Exception as e:
            log.error(
                "HTTP error in uploading a file to presigned URL: "
                f"{redact_secrets(e)}"
            )
            raise HTTPError(
                f"Failed to Upload File: {redact_secrets(e)}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

    @validate_args(
        evaluation_id=Rules.uuid_not_none,
        config=Rules.instance_of(EvalConfig),
        audio_groups=Rules.list_not_none,
    )
    def upload_session_json(self, evaluation_id: str, config: EvalConfig, audio_groups: List[AudioGroup]) -> None:
        """Upload session JSON data"""
        try:
            session_json = config.to_dict()
            session_json["files"] = [group.to_dict() for group in audio_groups]
            session_summary = self._session_json_summary(session_json)
            presigned_url = self.get_presigned_url(
                evaluation_id,
                "session.json",
                timeout=config.api_timeout,
                context=session_summary,
            )
            self.put_session_json(
                presigned_url,
                session_json,
                headers={"Content-type": "application/json"},
                timeout=config.upload_timeout,
                context={"evaluation_id": evaluation_id, **session_summary},
            )
        except Exception as e:
            raise HTTPError(f"Failed to upload session JSON: {redact_secrets(e)}")

    @validate_args(
        url=Rules.str_not_none,
        data=Rules.dict_not_none,
        headers=Rules.dict_not_none_or_none,
        timeout=Rules.make_type_rule((tuple, list)),
        context=Rules.dict_not_none_or_none,
    )
    def put_session_json(
        self,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Tuple[float, float] = EvalConfigDefault.UPLOAD_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
    ) -> Response:
        log.debug(f"Session JSON summary: {self._session_json_summary(data)}")
        if headers:
            log.debug(f"Session JSON header keys: {sorted(headers.keys())}")

        try:
            response = self.api_client.external_put(
                url,
                json_data=data,
                headers=headers,
                timeout=timeout,
                context=context,
            )
            response.raise_for_status()
            return response
        except Exception as e:
            log.error(
                "HTTP error in uploading a json to presigned url: "
                f"{redact_secrets(e)}"
            )
            raise HTTPError(
                "Failed to Upload JSON payload "
                f"({self._session_json_summary(data)}): {redact_secrets(e)}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

    def _session_json_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return non-sensitive shape information for session JSON diagnostics."""
        files = data.get("files")
        file_group_count = len(files) if isinstance(files, list) else 0
        audio_count = 0
        if isinstance(files, list):
            for group in files:
                if isinstance(group, dict) and isinstance(group.get("audios"), list):
                    audio_count += len(group["audios"])

        return {
            "top_level_keys": sorted(str(key) for key in data.keys()),
            "file_group_count": file_group_count,
            "audio_count": audio_count,
        }

    @validate_args(evaluation_id=Rules.uuid_not_none, output_dir=Rules.str_not_none)
    def download_evaluation_files_by_evaluation_id(self, evaluation_id: str, output_dir: str) -> str:
        """Download evaluation files using CloudFront cookies."""
        try:
            # Get the response from the API
            log.debug(f"Download evaluation files for evaluation {evaluation_id}")
            file_mata_json: Dict[str, List[Dict[str, Any]]] = {"files": []}
            response = self.api_client.get(f"evaluation-files/download?evaluation-id={evaluation_id}")
            response.raise_for_status()

            # Parse the response using EvaluationFileDownloadResponseDto
            download_response = response.json()

            # Ensure the output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Download each file using the original URL and cookies
            for file in tqdm(download_response["files"], desc="Downloading files", unit="file"):
                # Download the file using the original URL and cookies
                original_url = self._validate_download_original_url(
                    file["original_url"]
                )
                file_response = self.api_client.external_get(
                    original_url,
                    cookies=download_response["cookie"],
                    allow_redirects=False,
                )
                status_code = getattr(file_response, "status_code", None)
                if status_code is None or not 200 <= status_code < 300:
                    raise HTTPError(
                        "Download returned non-success status code "
                        f"{status_code}",
                        status_code=status_code,
                        response=file_response,
                    )
                file_response.raise_for_status()

                content_type = file_response.headers.get("Content-Type")
                file_extension = CONTENT_TYPE_TO_EXTENSION[content_type] if content_type else ".flac"

                # Generate a hash for the original file name
                file_original_name = file["original_name"]
                hash_object = hashlib.md5(file_original_name.encode(), usedforsecurity=False)
                hashed_file_name = hash_object.hexdigest()

                # Construct the file path using a sanitized model tag.
                safe_model_tag = self._safe_download_path_segment(
                    file.get("model_tag", "untagged")
                )
                file_path = self._safe_output_path(
                    output_dir,
                    safe_model_tag,
                    f"{hashed_file_name}{file_extension}",
                )

                self._write_download_file(file_path, file_response.content, output_dir)

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
            self._write_download_file(
                metadata_file_path,
                json.dumps(file_mata_json).encode("utf-8"),
                output_dir,
            )
            log.info(f"File metadata saved to {metadata_file_path}")

            return "Files downloaded successfully."
        except Exception as e:
            raise HTTPError(
                f"Failed to download evaluation files: {redact_secrets(e)}"
            )

    def _validate_download_original_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() != "https" or not host:
            raise ValueError("download original_url must be an HTTPS URL")

        if not self._is_allowed_download_host(host):
            raise ValueError("download original_url host is not allowed")
        return url

    def _is_allowed_download_host(self, host: str) -> bool:
        if os.getenv("PODONOS_ALLOW_UNTRUSTED_DOWNLOAD_HOSTS", "").lower() in _TRUTHY:
            return True

        configured_hosts = {
            item.strip().lower()
            for item in os.getenv("PODONOS_DOWNLOAD_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        if host in configured_hosts:
            return True

        return host in _PODONOS_DOWNLOAD_EXACT_HOSTS or host.endswith(
            _PODONOS_DOWNLOAD_HOST_SUFFIXES
        )

    def _safe_download_path_segment(self, value: Any) -> str:
        text = str(value or "untagged").replace("\\", "/")
        text = "_".join(part for part in text.split("/") if part not in {"", ".", ".."})
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._")
        return text or "untagged"

    def _safe_output_path(self, output_dir: str, *parts: str) -> str:
        output_root = os.path.abspath(output_dir)
        candidate = os.path.abspath(os.path.join(output_root, *parts))
        if os.path.commonpath([output_root, candidate]) != output_root:
            raise ValueError("Downloaded file path escapes output_dir")
        return candidate

    def _open_safe_download_file(self, file_path: str, output_dir: str) -> int:
        if os.name == "nt":
            parent = os.path.dirname(file_path)
            self._reject_symlink_components(output_dir, parent)
            os.makedirs(parent, exist_ok=True)
            self._reject_symlink_components(output_dir, parent)
            if os.path.islink(file_path):
                raise ValueError("download target file must not be a symlink")
            return os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        output_root = os.path.abspath(output_dir)
        candidate = os.path.abspath(file_path)
        if os.path.commonpath([output_root, candidate]) != output_root:
            raise ValueError("Downloaded file path escapes output_dir")

        os.makedirs(output_root, exist_ok=True)
        dir_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            dir_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            dir_flags |= os.O_NOFOLLOW

        file_name = os.path.basename(candidate)
        if file_name in {"", ".", ".."}:
            raise ValueError("download target file name is invalid")
        parent = os.path.dirname(candidate)
        rel_parent = os.path.relpath(parent, output_root)
        rel_parts = [] if rel_parent == "." else rel_parent.split(os.sep)

        dir_fds: List[int] = []
        try:
            current_fd = os.open(output_root, dir_flags)
            dir_fds.append(current_fd)
            for part in rel_parts:
                if part in {"", ".", ".."}:
                    raise ValueError("download target path component is invalid")
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                current_fd = os.open(part, dir_flags, dir_fd=current_fd)
                dir_fds.append(current_fd)

            file_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW
            return os.open(file_name, file_flags, 0o600, dir_fd=dir_fds[-1])
        except OSError as exc:
            raise ValueError("download target file path is not safe to write") from exc
        finally:
            for fd in reversed(dir_fds):
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _reject_symlink_components(self, output_dir: str, target_dir: str) -> None:
        output_root = os.path.abspath(output_dir)
        target_dir = os.path.abspath(target_dir)
        if os.path.commonpath([output_root, target_dir]) != output_root:
            raise ValueError("Downloaded file path escapes output_dir")
        current = output_root
        paths_to_check = [current]
        rel_dir = os.path.relpath(target_dir, output_root)
        if rel_dir != ".":
            for part in rel_dir.split(os.sep):
                if part in {"", ".", ".."}:
                    raise ValueError("download target path component is invalid")
                current = os.path.join(current, part)
                paths_to_check.append(current)
        for path in paths_to_check:
            if os.path.exists(path) and os.path.islink(path):
                raise ValueError("download target path must not contain symlinks")

    def _write_download_file(self, file_path: str, content: bytes, output_dir: str) -> None:
        fd = self._open_safe_download_file(file_path, output_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(content)

    @validate_args(evaluation_id=Rules.uuid_not_none, audios=Rules.list_not_none)
    def verify_files(
        self,
        evaluation_id: str,
        audios: List[Audio],
        timeout: Tuple[float, float] = EvalConfigDefault.VERIFY_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerifyFilesResponse:
        try:
            payload = {
                "files": [
                    {
                        "uploaded_file_name": audio.remote_object_name,
                        "content_md5": audio.content_md5,
                        "file_size": audio.file_size,
                    }
                    for audio in audios
                ]
            }
            endpoint = f"evaluations/{evaluation_id}/files/verify"
            response = self.api_client.post(
                endpoint,
                data=payload,
                timeout=timeout,
                context={
                    "method": "POST",
                    "endpoint": endpoint,
                    "evaluation_id": evaluation_id,
                    "file_count": len(audios),
                    **(context or {}),
                },
            )
            response.raise_for_status()
            return VerifyFilesResponse.from_dict(response.json())
        except Exception as e:
            raise HTTPError(
                f"Failed to verify evaluation files: {e}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

    @validate_args(evaluation_id=Rules.uuid_not_none, file_meta_ids=Rules.list_not_none_or_none)
    def process_files(
        self,
        evaluation_id: str,
        file_meta_ids: Optional[List[str]] = None,
        timeout: Tuple[float, float] = EvalConfigDefault.API_TIMEOUT,
        context: Optional[Dict[str, Any]] = None,
    ) -> ProcessFilesResponse:
        try:
            payload: Dict[str, Any] = {"file_meta_ids": file_meta_ids} if file_meta_ids else {}
            endpoint = f"evaluations/{evaluation_id}/files/process"
            response = self.api_client.post(
                endpoint,
                data=payload,
                timeout=timeout,
                context={
                    "endpoint": endpoint,
                    "evaluation_id": evaluation_id,
                    "file_count": len(file_meta_ids or []),
                    **(context or {}),
                },
            )
            response.raise_for_status()
            return ProcessFilesResponse.from_dict(response.json())
        except Exception as e:
            raise HTTPError(
                f"Failed to trigger file processing: {e}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )
