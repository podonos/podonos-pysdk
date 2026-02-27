import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from podonos.common.exception import HTTPError
from podonos.common.util import get_content_type_by_filename
from podonos.common.validator import Rules, validate_args
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.entity.flash_eval import FlashEvalResult

MAX_UPLOAD_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


class FlashEvalService:
    """Service class for flash auto-evaluation API."""

    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    @validate_args(file_path=Rules.file_path_not_none)
    def eval(self, file_path: str) -> FlashEvalResult:
        """Run auto-evaluation on an audio file.

        Executes the 3-step flow: init -> upload -> eval.

        Args:
            file_path: Path to the audio file to evaluate.

        Returns:
            FlashEvalResult with naturalness score.

        Raises:
            HTTPError: If any API call fails.
        """
        filename = os.path.basename(file_path)
        mimetype = get_content_type_by_filename(file_path)

        # Step 1: Initialize and get presigned URL
        key, presigned_url = self._init(filename=filename, mimetype=mimetype)

        # Step 2: Upload file to object storage
        self._upload(presigned_url=presigned_url, file_path=file_path, mimetype=mimetype)

        # Step 3: Request evaluation
        return self._eval(key=key)

    @validate_args(filename=Rules.str_non_empty, mimetype=Rules.str_non_empty)
    def _init(self, filename: str, mimetype: str) -> Tuple[str, str]:
        """Step 1: Initialize upload and get presigned URL + key.

        Returns:
            Tuple of (upload_key, presigned_url).
        """
        log.debug("Flash eval: initializing upload")
        try:
            payload: Dict[str, Any] = {
                "files": [
                    {
                        "filename": filename,
                        "filetype": "TARGET_1",
                        "mimetype": mimetype,
                    }
                ]
            }
            response = self.api_client.post("flash/v1/init", data=payload)
            response.raise_for_status()

            data = response.json()
            upload_key = data.get("key")
            if upload_key is None:
                raise HTTPError("Flash eval init response missing 'key' field")
            if not upload_key:
                raise HTTPError("Flash eval init response returned empty 'key' field")
            urls = data.get("urls", [])
            if not urls:
                raise HTTPError("Flash eval init returned no upload URLs")
            presigned_url = urls[0]
            log.debug(f"Flash eval: received key={upload_key}")
            return upload_key, presigned_url
        except HTTPError:
            raise
        except Exception as e:
            resp = getattr(e, "response", None)
            raise HTTPError(
                f"Failed to initialize flash eval: {e}",
                status_code=getattr(resp, "status_code", None),
                response=resp,
            ) from e

    @validate_args(presigned_url=Rules.str_non_empty, file_path=Rules.file_path_not_none, mimetype=Rules.str_non_empty)
    def _upload(self, presigned_url: str, file_path: str, mimetype: str) -> None:
        """Step 2: Upload file to object storage via presigned URL."""
        log.debug(f"Flash eval: uploading {file_path}")
        file_size = os.path.getsize(file_path)
        if file_size > MAX_UPLOAD_FILE_SIZE:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds maximum ({MAX_UPLOAD_FILE_SIZE} bytes)"
            )
        # Read file into memory for retry safety: if the upload fails and APIClient
        # retries, a file handle would be at EOF and send empty data on the next attempt.
        with open(file_path, "rb") as f:
            file_data = f.read()
        try:
            response = self.api_client.external_put(
                presigned_url,
                data=file_data,
                headers={
                    "Content-Type": mimetype,
                    "x-goog-resumable": "false",
                },
            )
            response.raise_for_status()
            log.debug("Flash eval: upload complete")
        except Exception as e:
            resp = getattr(e, "response", None)
            raise HTTPError(
                f"Failed to upload file for flash eval: {e}",
                status_code=getattr(resp, "status_code", None),
                response=resp,
            ) from e

    @validate_args(key=Rules.str_non_empty)
    def _eval(self, key: str) -> FlashEvalResult:
        """Step 3: Request evaluation for the uploaded file."""
        log.debug("Flash eval: requesting evaluation")
        try:
            payload: Dict[str, Any] = {
                "key": key,
                "request_time": datetime.now(timezone.utc).isoformat(),
            }
            # Extended read timeout (180s) to handle model cold start latency (~150s).
            response = self.api_client.post("flash/v1/eval", data=payload, timeout=(5, 180))
            response.raise_for_status()

            return FlashEvalResult.from_dict(response.json())
        except Exception as e:
            resp = getattr(e, "response", None)
            raise HTTPError(
                f"Failed to get flash eval result: {e}",
                status_code=getattr(resp, "status_code", None),
                response=resp,
            ) from e
