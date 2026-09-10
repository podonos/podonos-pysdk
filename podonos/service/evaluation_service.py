import hashlib
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, TypeVar
from urllib.parse import urlparse

from requests import Response
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException
from requests.exceptions import HTTPError as RequestsHTTPError
from requests.exceptions import Timeout as RequestsTimeout
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
from podonos.entity.evaluation import EvaluationEntity, EvaluationProgress
from podonos.entity.verification import ProcessFilesResponse, VerifyFilesResponse
from podonos.errors.error import EvaluationNotFoundError


_PollSentinel = TypeVar("_PollSentinel")
_TRUTHY = {"1", "true", "yes", "y", "on"}
# Statuses the auto_start poll treats as "not ready yet" rather than as an answer. APIClient
# already retries these itself and raises once its own attempts are exhausted, so the poll loop
# absorbs that exception as one more tick instead of letting a rate-limit blip end a 30-minute
# close(). Note that 409 is deliberately absent: it never reaches APIClient's retry set, so it
# arrives as a returned Response and is classified below.
#
# The two poll methods below carry no blanket `except Exception`, unlike every other method in
# this file. That wrapper would run before the `except RequestsHTTPError` clause and silently
# swallow the retryable classification, turning an absorbed 429 into a terminal failure. Do not
# add one when copying these methods.
_RETRYABLE_POLL_STATUS = {408, 429, 500, 502, 503, 504}
# 409 is the backend's "not ready yet" / "another request is mid-start". It never reaches
# APIClient's retry set, so it arrives as a returned Response rather than as an exception --
# which is why it belongs here and not above.
_NOT_READY_POLL_STATUS = _RETRYABLE_POLL_STATUS | {409}
# The two 401 codes GET evaluations/{id}/progress uses for "not an evaluation you can see":
# the id is unknown or the key's creator is not a member, and the key belongs to another
# workspace. Any other 401 is about the credential, not the evaluation.
_NOT_IN_WORKSPACE_CODES = {"UNAUTHORIZED_TO_ACCESS_WORKSPACE", "UNAUTHORIZED_TO_ACCESS_EVALUATION"}

# How the two auto_start endpoints answer, so a reader here does not have to reconstruct it from
# the code below. The asymmetry in the last row is what makes the two-phase poll correct rather
# than merely tidy.
#
#   GET evaluations/{id}/validate          POST evaluations/{id}/start
#   ------------------------------------   ------------------------------------------------
#   200 empty body -> ready                200 -> read `status`; ACTIVE/COMPLETED is success
#   409 AUDIO_FILES_NOT_READY -> poll      409 START_IN_PROGRESS / NOT_READY -> retry
#   429, 5xx -> poll                       429, 5xx -> retry
#   400 INVALID_AUDIO_FILES -> terminal    400 AUTO_START_NOT_ENABLED -> terminal
#   400 NO_EVALUATION_FILES -> terminal    400 NOT_STARTABLE (DELETED/CANCELED) -> terminal
#
#   400 EVALUATION_NOT_DRAFT for ANY       ACTIVE/COMPLETED report the current state and do
#   non-DRAFT evaluation                   not start again; DELETED/CANCELED are rejected
#
# Both endpoints are rate limited per API key, which is why the caller backs off rather than
# polling tightly. Success is never inferred from an error code: it is the `status` field of a
# 200. The start response carries evaluation_id, status, internal_status and started_time.
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
        except RequestsHTTPError as e:
            # The server rejected the request (e.g. an unsupported language). Surface its own
            # message + detail, and carry the status code, instead of an opaque wrapper.
            resp = e.response if e.response is not None else response
            raise HTTPError(
                f"Failed to create the evaluation: {self._create_error_message(resp)}",
                status_code=resp.status_code,
                response=resp,
            )
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
        except RequestsHTTPError as e:
            resp = e.response if e.response is not None else response
            raise HTTPError(
                f"Failed to create the evaluation: {self._create_error_message(resp)}",
                status_code=resp.status_code,
                response=resp,
            )
        except Exception as e:
            raise HTTPError(f"Failed to create the evaluation: {e}")

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def find_evaluation_in_workspace(
        self,
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> EvaluationEntity:
        """Find one evaluation among the workspace's evaluations.

        Reads the evaluation list rather than the single-evaluation endpoint, which an API key
        cannot access. That is what broke resume_evaluator in 0.41.0, so do not route this back
        to a per-id read without checking that an API key can reach it. Only the matching row
        is parsed, so a malformed unrelated evaluation in the workspace cannot block a resume.
        """
        endpoint = "evaluations"
        try:
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
            evaluations = response.json()
        except Exception as e:
            raise HTTPError(
                f"Failed to read the workspace evaluation list while resuming "
                f"{evaluation_id}: {e}"
            )

        # Anything but a list is the endpoint changing shape, not a missing evaluation. Say so
        # here: an envelope like {"items": [...]} would otherwise iterate its keys, match
        # nothing, and blame the caller's id or API key for an evaluation that is present.
        if not isinstance(evaluations, list):
            raise HTTPError(
                f"Evaluation list came back as {type(evaluations).__name__}, not a list"
            )

        row = next(
            (
                item
                for item in evaluations
                if isinstance(item, dict) and item.get("id") == evaluation_id
            ),
            None,
        )
        if row is None:
            raise EvaluationNotFoundError(
                f"Evaluation {evaluation_id} is not in this workspace. It may have been "
                "deleted or hidden, or the API key may belong to a different workspace."
            )
        try:
            return EvaluationEntity.from_dict(row)
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            # from_dict embeds the whole row in its message, so redact and clip it the way
            # every other server-data error in this file does.
            raise HTTPError(
                f"Evaluation {evaluation_id} came back in an unexpected shape: "
                f"{redact_secrets(e)[:200]}"
            )

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def get_evaluation_progress(
        self,
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> EvaluationProgress:
        """Read one evaluation's status and progress.

        The public contract (completion gate, rate limit, what each error means) lives on
        ``Client.get_evaluation_progress``; this method only maps the wire to it.

        Raises:
            EvaluationNotFoundError: the backend answered 401 with a workspace-scoped code,
                which is how it reports an id it will not confirm exists.
            HTTPError: anything else, including a 401 for a bad or revoked key and a 404
                from a backend that does not serve this endpoint yet.
        """
        endpoint = f"evaluations/{evaluation_id}/progress"
        try:
            kwargs: Dict[str, Any] = {}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if context is not None:
                request_context = dict(context)
                request_context["endpoint"] = endpoint
                request_context["evaluation_id"] = evaluation_id
                kwargs["context"] = request_context
            response = self.api_client.get(endpoint, **kwargs)
        except Exception as e:
            raise HTTPError(
                f"Failed to get the progress of evaluation {evaluation_id}: {e}",
                status_code=getattr(getattr(e, "response", None), "status_code", None),
            )

        if response.status_code == 401:
            # Only the two workspace-scoped codes mean "not your evaluation". A missing or
            # revoked key is also a 401, and reporting that as a deleted evaluation would send
            # the operator chasing the wrong problem.
            error_code, error_message = self._parse_error_body(response)
            if error_code in _NOT_IN_WORKSPACE_CODES:
                raise EvaluationNotFoundError(
                    f"Evaluation {evaluation_id} is not in this workspace. It may have been "
                    "deleted, or the API key may belong to a different workspace."
                )
            raise HTTPError(
                f"Failed to get the progress of evaluation {evaluation_id}: "
                f"{' '.join(str(part) for part in (error_code, error_message) if part)}".strip(),
                status_code=401,
                response=response,
            )
        if response.status_code == 404:
            # Distinct from the 401 above on purpose. The route itself is missing, which means
            # the backend has not deployed it, and reporting that as a missing evaluation would
            # send the caller looking for the wrong problem.
            raise HTTPError(
                "This Podonos backend does not serve evaluation progress yet. Retry once the "
                "backend is updated, or read progress from get_evaluation_list().",
                status_code=404,
                response=response,
            )

        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            raise HTTPError(
                f"Failed to get the progress of evaluation {evaluation_id}: {e}",
                status_code=response.status_code,
                response=response,
            )

        try:
            return EvaluationProgress.from_dict(payload)
        except (KeyError, ValueError, AttributeError, TypeError) as e:
            # from_dict embeds the whole payload in its message, so redact and clip it the way
            # every other server-data error in this file does.
            raise HTTPError(
                f"Progress for evaluation {evaluation_id} came back in an unexpected shape: "
                f"{redact_secrets(e)[:200]}"
            )

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def validate_evaluation(
        self,
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Ask whether the evaluation's files are ready to be paid for and started.

        This endpoint is meaningful only while the evaluation is DRAFT: it answers
        400 BAD_REQUEST_EVALUATION_NOT_DRAFT for anything else. Callers must stop polling it
        once a start has been issued.

        Returns:
            True when the files are ready, False when the caller should poll again.

        Raises:
            HTTPError: On a terminal response, carrying the wire error_code and error_message.
        """
        endpoint = f"evaluations/{evaluation_id}/validate"
        try:
            response = self.api_client.get(endpoint, **self._poll_kwargs(evaluation_id, timeout, context))
        except RequestsHTTPError as e:
            return self._absorb_or_raise(e, "validate evaluation", sentinel=False)
        except (RequestsConnectionError, RequestsTimeout) as e:
            # The request never got an answer, which says nothing about readiness. The caller's
            # deadline still bounds the loop.
            log.debug(f"Readiness check for {evaluation_id} did not reach the server: {e}")
            return False
        except RequestException as e:
            # Anything else from requests is a real failure, not a tick. Wrap it so callers see
            # the HTTPError this method documents rather than a raw transport exception.
            raise HTTPError(f"Failed to validate evaluation: {e}")

        if response.ok:
            return True
        if response.status_code in _NOT_READY_POLL_STATUS:
            return False
        raise self._poll_error(response, "validate evaluation")

    @validate_args(evaluation_id=Rules.uuid_not_none)
    def start_evaluation(
        self,
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Start the evaluation, charging the workspace balance.

        The endpoint is idempotent and returns the evaluation's current state, so calling it on
        an already-started evaluation reports that state without charging again. Success is read
        from the returned status, never inferred from an error code.

        Returns:
            The evaluation's status on a 2xx, or None when the caller should retry.

        Raises:
            HTTPError: On a terminal response, carrying the wire error_code and error_message.
        """
        endpoint = f"evaluations/{evaluation_id}/start"
        try:
            response = self.api_client.post(endpoint, data={}, **self._poll_kwargs(evaluation_id, timeout, context))
        except RequestsHTTPError as e:
            return self._absorb_or_raise(e, "start evaluation", sentinel=None)
        except (RequestsConnectionError, RequestsTimeout) as e:
            # The start may well have succeeded with only the response lost. Retrying an
            # idempotent start is what resolves that; raising here would report failure on an
            # evaluation the user has already been charged for.
            log.debug(f"Start request for {evaluation_id} did not get an answer: {e}")
            return None
        except RequestException as e:
            raise HTTPError(f"Failed to start evaluation: {e}")

        if response.ok:
            try:
                return response.json().get("status")
            except (ValueError, AttributeError) as e:
                # A 2xx whose body is not the expected object tells us nothing. Treat it as a tick
                # rather than letting a raw requests exception escape this service.
                # Narrow rather than blanket, deliberately: requests.exceptions.JSONDecodeError
                # subclasses ValueError, and a body that parses to a list gives AttributeError on
                # .get, so these two cover the case without swallowing anything else.
                log.warning(f"Could not read the start response for {evaluation_id}: {e}")
                return None
        if response.status_code in _NOT_READY_POLL_STATUS:
            return None
        raise self._poll_error(response, "start evaluation")

    @staticmethod
    def _poll_kwargs(
        evaluation_id: str,
        timeout: Optional[Tuple[float, float]],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the timeout/context kwargs the poll endpoints share."""
        kwargs: Dict[str, Any] = {"context": {**(context or {}), "evaluation_id": evaluation_id}}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return kwargs

    def _absorb_or_raise(self, error: RequestsHTTPError, action: str, sentinel: _PollSentinel) -> _PollSentinel:
        """Absorb an exhausted transport retry as a poll tick, or re-raise it as terminal.

        The raising branches are unreachable while _RETRYABLE_POLL_STATUS stays set-equal to
        APIClient's default retry_status_codes: only those statuses reach here as an exception,
        and all of them are absorbed. They exist so that the two drifting apart surfaces as a
        terminal error rather than as silently swallowed.
        """
        # requests.HTTPError.response is Optional, hence the same getattr chain used elsewhere
        # in this file.
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if status in _RETRYABLE_POLL_STATUS:
            log.debug(f"Failed to {action} with a retryable status ({status}); treating as not ready")
            return sentinel
        if response is None:
            raise HTTPError(f"Failed to {action}: {error}", status_code=status)
        raise self._poll_error(response, action)

    def _poll_error(self, response: Response, action: str) -> HTTPError:
        """Build the terminal error, carrying the wire error_code and error_message."""
        error_code, error_message = self._parse_error_body(response)
        detail = " ".join(str(part) for part in (error_code, error_message) if part)
        return HTTPError(
            f"Failed to {action}: {detail}".strip(),
            status_code=response.status_code,
            response=response,
        )

    @staticmethod
    def _parse_error_body(response: Response) -> Tuple[Optional[str], Optional[str]]:
        """Pull error_code and error_message off an error body.

        Falls back to the raw text for a body that is not the expected JSON, such as the HTML a
        proxy returns on a 502.
        """
        def _clip(value: Any) -> Optional[str]:
            return None if value is None else redact_secrets(str(value))[:200]

        try:
            body = response.json()
            return _clip(body.get("error_code")), _clip(body.get("error_message"))
        except Exception:
            return None, _clip(response.text)

    def _create_error_message(self, response: Response) -> str:
        """Build a message from the {error_code, error_message, detail} error envelope.

        For a rejected field (e.g. an unsupported language) the backend's validation handler
        puts a generic string in error_message and the field-specific reason in detail, so we
        include detail to keep the message actionable.
        """
        error_code, error_message = self._parse_error_body(response)
        detail: Optional[str] = None
        try:
            raw = response.json().get("detail")
            detail = None if raw is None else redact_secrets(str(raw))[:200]
        except Exception:
            detail = None
        parts = [p for p in (error_message, detail) if p]
        return " ".join(parts) if parts else (error_code or "request rejected")

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
        each file dict. This is forward-compat metadata: the backend currently
        ignores the field (DTO uses Pydantic extra="ignore", so there is no
        validation error) and de-duplicates retried/lost-response POSTs on the slot
        (file_meta_id, group, order) under an advisory lock. The same `data` dict is
        reused across the HTTP-transport retry in ``api._execute_with_retry`` (the
        closure captures one body), so the key is byte-stable across retries for
        free. When None (e.g. callers that do not compute keys), the body is built
        exactly as before.
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
