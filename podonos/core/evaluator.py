import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from podonos.common.enum import EvalType
from podonos.common.redaction import redact_secrets
from podonos.common.util import calculate_file_md5_base64
from podonos.common.validator import Rules, validate_args
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig
from podonos.core.file import Audio, AudioGroup, File, FileTransformer, FileValidator
from podonos.core.upload_ledger import (
    UploadLedger,
    UploadLedgerRow,
    build_upload_manifest_hash,
    build_upload_manifest_key,
)
from podonos.core.upload_manager import UploadManager
from podonos.entity.evaluation import EvaluationEntity
from podonos.entity.verification import FileVerificationResult, VerifyFilesResponse
from podonos.errors.error import FileVerificationFailure, UploadRetryExhaustedError
from podonos.service.evaluation_service import EvaluationService

MAX_UPLOAD_RETRIES = 3


class Evaluator:
    """Base class for all evaluators."""

    _api_client: APIClient
    _eval_config: EvalConfig
    _evaluation: Optional[EvaluationEntity] = None
    _evaluation_service: EvaluationService
    _file_transformer: FileTransformer
    _file_validator: FileValidator
    _supported_eval_types: List[EvalType]
    _initialized: bool = False
    _upload_manager: Optional[UploadManager] = (
        None  # Upload manager. Lazy initialization when used for saving resources.
    )
    _upload_ledger: Optional[UploadLedger] = None
    _ordered_file_groups: List[AudioGroup]  # ordered evaluation files groups
    _next_file_index: int = 0

    def __init__(
        self,
        api_client: APIClient,
        eval_config: EvalConfig,
        supported_eval_types: List[EvalType],
    ):
        """Initialize the evaluator.

        Args:
            api_client: API client for making requests
            eval_config: Optional evaluation configuration
        """
        self._initialized = True
        self._validate_initialization(api_client, eval_config, supported_eval_types)
        self._initialize_attributes(api_client, eval_config, supported_eval_types)

    @validate_args(
        api_client=Rules.instance_of(APIClient),
        eval_config=Rules.instance_of(EvalConfig),
        supported_eval_types=Rules.list_not_none,
    )
    def _validate_initialization(
        self,
        api_client: APIClient,
        eval_config: EvalConfig,
        supported_eval_types: List[EvalType],
    ) -> None:
        """Validate the initialization parameters.

        Args:
            api_client: API client to validate
            eval_config: Evaluation configuration to validate

        Raises:
            ValueError: If api_client is not initialized
            ValueError: If eval_config is not initialized
        """
        if not api_client:
            raise ValueError("api_client is not initialized.")
        if not eval_config:
            raise ValueError("eval_config is not initialized.")
        if eval_config.eval_type not in supported_eval_types:
            raise ValueError("Not supported evaluation type")

    @validate_args(
        api_client=Rules.instance_of(APIClient),
        eval_config=Rules.instance_of(EvalConfig),
        supported_eval_types=Rules.list_not_none,
    )
    def _initialize_attributes(
        self,
        api_client: APIClient,
        eval_config: EvalConfig,
        supported_eval_types: List[EvalType],
    ) -> None:
        """Initialize class attributes.

        Args:
            api_client: API client for making requests
            eval_config: Evaluation configuration
        """
        self._api_client = api_client
        self._eval_config = eval_config
        self._evaluation_service = EvaluationService(api_client)
        self._upload_ledger = self._initialize_upload_ledger(eval_config)
        self._evaluation = self._set_evaluation(eval_config)
        self._file_transformer = FileTransformer(eval_config)
        self._file_validator = FileValidator(eval_config)
        self._supported_eval_types = supported_eval_types
        self._ordered_file_groups = []
        self._upload_manager = None
        self._bind_upload_ledger_contract(eval_config)
        self._next_file_index = 0

    def _initialize_upload_ledger(
        self, eval_config: EvalConfig
    ) -> Optional[UploadLedger]:
        if not eval_config.resume_upload:
            return None
        return UploadLedger(eval_config.resolve_upload_state_path())

    def _session_config_contract(self, eval_config: EvalConfig) -> Dict[str, Any]:
        session_config = dict(eval_config.to_dict())
        session_config.pop("eval_id", None)
        return session_config

    def _build_upload_ledger_contract(self, eval_config: EvalConfig) -> Dict[str, Any]:
        return {
            "evaluation_id": self.get_evaluation_id(),
            "eval_type": eval_config.eval_type.value,
            "eval_language": eval_config.eval_language.value,
            "eval_batch_size": eval_config.eval_batch_size,
            "eval_template_id": eval_config.eval_template_id,
            "use_annotation": eval_config.eval_use_annotation,
            "use_loudness_normalization": eval_config.use_loudness_normalization,
            "session_config": self._session_config_contract(eval_config),
        }

    def _bind_upload_ledger_contract(self, eval_config: EvalConfig) -> None:
        if self._upload_ledger is None:
            return

        existing = self._upload_ledger.get_evaluation_contract(self.get_evaluation_id())
        if existing is None:
            if eval_config.resume_evaluation_id:
                raise ValueError(
                    "Upload ledger is missing the original evaluation contract; "
                    "cannot safely resume this evaluation."
                )
            contract = self._build_upload_ledger_contract(eval_config)
            self._upload_ledger.set_evaluation_contract(
                self.get_evaluation_id(), contract
            )
            return

        contract = self._build_upload_ledger_contract(eval_config)
        mismatches = {
            key: (existing.get(key), value)
            for key, value in contract.items()
            if key != "evaluation_id" and existing.get(key) != value
        }
        if mismatches:
            details = ", ".join(sorted(mismatches))
            raise ValueError(
                "Upload ledger evaluation contract does not match the current "
                f"resume configuration (mismatched keys: {details}). "
                "Start a fresh evaluation or resume with the original SDK "
                "configuration."
            )

    def _store_upload_ledger_contract(self) -> None:
        if self._upload_ledger is None:
            return
        self._upload_ledger.set_evaluation_contract(
            self.get_evaluation_id(),
            self._build_upload_ledger_contract(self._eval_config),
        )

    @validate_args(method_name=Rules.str_non_empty)
    def _validate_eval_type(self, method_name: str) -> None:
        """Validate if the evaluation type is supported for the given method.

        Args:
            method_name: Name of the method being validated ('add_file' or 'add_files')

        Raises:
            ValueError: If evaluation type is not supported for the method
        """
        if method_name == "add_file":
            supported_types = [
                EvalType.NMOS,
                EvalType.QMOS,
                EvalType.P808,
                EvalType.CUSTOM_SINGLE,
            ]
            error_msg = (
                f"The '{method_name}' is only supported for single file evaluation types: "
                f"{supported_types}"
            )
        elif method_name == "add_ranking_set":
            supported_types = [EvalType.RANKING]
            error_msg = (
                f"The '{method_name}' is only supported for ranking evaluation types: "
                f"{supported_types}"
            )
        else:  # add_files
            supported_types = [
                EvalType.CMOS,
                EvalType.DMOS,
                EvalType.PREF,
                EvalType.SMOS,
                EvalType.CSMOS,
                EvalType.CUSTOM_DOUBLE,
            ]
            error_msg = (
                f"The '{method_name}' is only supported for comparison evaluation types: "
                f"{supported_types}"
            )

        if self._eval_config.eval_type not in supported_types:
            raise ValueError(error_msg)

    def get_evaluation_id(self) -> str:
        """Get the evaluation ID.

        Returns:
            str: Evaluation ID

        Raises:
            AssertionError: If evaluation is not initialized
        """
        assert self._evaluation, "Evaluation not initialized"
        return self._evaluation.id

    def close(self) -> Dict[str, str]:
        self._validate_close()
        if self._eval_config.eval_type == EvalType.RANKING:
            self._update_ranking_batch_size_before_upload()
            self._store_upload_ledger_contract()
        self._wait_for_uploads()
        self._process_audio_files_with_verification()
        self._upload_session_json()
        self._cleanup()
        return {"status": "ok"}

    @validate_args(file=Rules.instance_of(File))
    def add_file(self, file: File) -> None:
        """Add new file for speech evaluation.
        The file may be either in {wav, mp3} format. The file will be securely uploaded to
        Podonos service system.

        Args:
            file: File object including the path, the model tag, the other tags, and the script.

        Example:
        If you want to evaluate each audio file separately (e.g., Naturalness MOS):
            add_file(file=File(path='./test.wav', model_tag='my_new_model1', tags=['male', 'generated'],
                               script='hello there'))

        Returns: None

        Raises:
            ValueError: if this function is called before calling init()
            FileNotFoundError: if a given file is not found.
        """
        if not self._initialized:
            raise ValueError("Try to add file once the evaluator is closed.")

        self._validate_eval_type("add_file")

        if file.script_tags:
            raise ValueError(
                "script_tags is only supported for RANKING evaluations. "
                "Use add_ranking_set() instead."
            )

        file = self._file_validator.validate_file(file)
        audio_group = self._file_transformer.transform_into_audio_group([file])
        self._ordered_file_groups.append(audio_group)
        self._upload_one_file(
            evaluation_id=self.get_evaluation_id(), audio=audio_group.audios[0]
        )

    @validate_args(
        file0=Rules.instance_of(File),
        file1=Rules.instance_of(File),
        file2=Rules.optional_instance_of(File),
    )
    def add_files(self, file0: File, file1: File, file2: Optional[File] = None) -> None:
        """Add two files for speech evaluation. The files will be securely uploaded to Podonos service system.

        The order of files is maintained based on evaluation type:
        - PREF, CUSTOM_DOUBLE: Files are ordered stimulus
        - SMOS: Files are unordered stimulus
        - CMOS, DMOS: One file must be reference, one must be stimulus
        - CSMOS: One file must be reference, two must be stimulus

        Args:
            file0: First audio file
            file1: Second audio file
            file2: Third audio file

        Example:
        If you want to evaluate audio files together (e.g., Comparative MOS):
            f0 = File(path="/path/to/generated.wav", model_tag='my_new_model1', tags=['male', 'english'], is_ref=True)
            f1 = File(path="/path/to/original.wav", model_tag='my_new_model2', tags=['male', 'english', 'param1'])
            add_files(file0=f0, file1=f1)

        If you want to evaluate two stimuli with a reference:
            ref = File(path="/path/to/reference.wav", model_tag='my_new_model3', tags=['male', 'english'], is_ref=True)
            add_files(file0=f0, file1=f1, file2=ref)

        Returns: None

        Raises:
            ValueError: If evaluator not initialized or invalid file configuration
        """
        if not self._initialized:
            raise ValueError("Evaluator is not initialized")

        self._validate_eval_type("add_files")

        if any(f.script_tags for f in [file0, file1, file2] if f is not None):
            raise ValueError(
                "script_tags is only supported for RANKING evaluations. "
                "Use add_ranking_set() instead."
            )

        files = self._file_validator.validate_files([file0, file1, file2])
        audio_group = self._file_transformer.transform_into_audio_group(files)
        self._ordered_file_groups.append(audio_group)
        for audio in audio_group.audios:
            self._upload_one_file(evaluation_id=self.get_evaluation_id(), audio=audio)

    @validate_args(files=Rules.list_not_none)
    def add_ranking_set(self, files: List[File]) -> None:
        """Add one ranking set (ordered candidates) for RANKING evaluation.

        Constraints enforced across calls:
        - All groups must have the same number of files.
        - Order of model_tag must be identical across groups.
        - Files must be stimuli (no reference).
        """
        if not self._initialized:
            raise ValueError("Evaluator is not initialized")

        self._validate_eval_type("add_ranking_set")

        validated_files = self._file_validator.validate_files(files)
        audio_group = self._file_transformer.transform_into_audio_group(validated_files)
        self._ordered_file_groups.append(audio_group)
        if self._eval_config.resume_upload:
            try:
                self._update_ranking_batch_size_before_upload()
                self._store_upload_ledger_contract()
            except Exception:
                self._ordered_file_groups.pop()
                raise
        for audio in audio_group.audios:
            self._upload_one_file(evaluation_id=self.get_evaluation_id(), audio=audio)

    def _validate_close(self) -> None:
        """Validate the state before closing.

        Raises:
            ValueError: If session is not properly initialized
        """
        if not self._initialized or not self._eval_config:
            raise ValueError("No evaluation session is open.")

    def _wait_for_uploads(self) -> None:
        """Wait for all file uploads to complete."""
        log.debug("Wait until the upload manager shuts down all the upload workers")
        assert self._upload_manager and self._upload_manager.wait_and_close()

    def _process_audio_files_with_verification(self) -> None:
        log.info("Uploading file metadata...")
        all_audios = [
            audio for group in self._ordered_file_groups for audio in group.audios
        ]
        audios_for_metadata = self._get_audios_needing_metadata_registration(
            all_audios
        )

        self._register_metadata_for_audios(audios_for_metadata)

        audios_for_verification = self._get_audios_needing_verification(all_audios)

        log.info(f"Verifying {len(audios_for_verification)} files...")
        verify_response = self._verify_files_in_batches(
            self.get_evaluation_id(), audios_for_verification
        )

        if verify_response.all_verified:
            log.info(
                f"All {verify_response.verified_count} files verified successfully."
            )
        else:
            failed_results = [r for r in verify_response.results if not r.verified]
            failed_audios = self._get_failed_audios(all_audios, failed_results)

            for retry_num in range(1, MAX_UPLOAD_RETRIES + 1):
                log.warning(
                    f"{len(failed_audios)} files failed verification, "
                    f"retrying ({retry_num}/{MAX_UPLOAD_RETRIES})..."
                )

                self._retry_failed_uploads(failed_audios)
                verify_response = self._verify_files_in_batches(
                    self.get_evaluation_id(), failed_audios
                )

                if verify_response.all_verified:
                    log.info(
                        f"All files verified successfully after {retry_num} retry(ies)."
                    )
                    break

                failed_results = [r for r in verify_response.results if not r.verified]
                failed_audios = self._get_failed_audios(failed_audios, failed_results)
            else:
                failures = [
                    FileVerificationFailure(
                        uploaded_file_name=r.uploaded_file_name,
                        original_name=self._find_original_name(r.uploaded_file_name),
                        error_code=r.error.code if r.error else "UNKNOWN",
                        message=r.error.message if r.error else "Unknown error",
                        expected=r.error.expected if r.error else None,
                        actual=r.error.actual if r.error else None,
                    )
                    for r in failed_results
                ]
                raise UploadRetryExhaustedError(
                    f"Upload verification failed after {MAX_UPLOAD_RETRIES} retries. "
                    f"{len(failures)} file(s) could not be verified:",
                    failures=failures,
                    retry_count=MAX_UPLOAD_RETRIES,
                    max_retries=MAX_UPLOAD_RETRIES,
                )

        silent_audios = [
            audio for group in self._ordered_file_groups
            for audio in group.audios
            if audio.is_silent
        ]
        if silent_audios:
            silent_names = [os.path.basename(a.path) for a in silent_audios]
            MAX_DISPLAY = 10
            displayed = ', '.join(silent_names[:MAX_DISPLAY])
            suffix = f" (and {len(silent_names) - MAX_DISPLAY} more)" if len(silent_names) > MAX_DISPLAY else ""
            log.warning(
                f"{len(silent_audios)} file(s) detected as near-silent audio: "
                f"{displayed}{suffix}. "
                f"These files may not contain audible content and could affect evaluation results."
            )

        log.info("Triggering file processing...")
        process_request_hash = self._finalization_hash(
            {
                "evaluation_id": self.get_evaluation_id(),
                "files": [audio.to_create_file_dict() for audio in all_audios],
            }
        )
        if self._upload_ledger is not None and self._upload_ledger.is_processed(
            self.get_evaluation_id(), process_request_hash
        ):
            log.info("Skipping file processing; upload ledger marks it complete.")
            return
        process_response = self._evaluation_service.process_files(
            self.get_evaluation_id(),
            timeout=self._eval_config.api_timeout,
            context={"file_count": len(all_audios)},
        )
        if self._upload_ledger is not None:
            self._upload_ledger.mark_processed(
                self.get_evaluation_id(),
                process_response.processing_count,
                process_request_hash,
            )
        log.info(f"Processing triggered for {process_response.processing_count} files.")

    def _verify_files_in_batches(
        self, evaluation_id: str, audios: List[Audio]
    ) -> VerifyFilesResponse:
        """Verify files in batches to avoid timeout issues with large file counts.

        Args:
            evaluation_id: The evaluation ID
            audios: List of audio files to verify

        Returns:
            VerifyFilesResponse: Aggregated verification response from all batches
        """
        all_results: List[FileVerificationResult] = []
        total_verified = 0
        total_failed = 0
        audios_to_verify: List[Audio] = []

        for audio in audios:
            row = self._get_ledger_row(audio)
            if row and row.status == "verified":
                if not self._ledger_row_matches_local_file(audio, row):
                    raise ValueError(
                        "Upload ledger row does not match the current local file for "
                        "the current upload item. Start a fresh evaluation or remove the stale "
                        "ledger row before resuming."
                    )
                self._hydrate_audio_from_ledger(audio, row)
                total_verified += 1
                continue
            audios_to_verify.append(audio)

        batch_size = self._eval_config.verify_batch_size

        for i in range(0, len(audios_to_verify), batch_size):
            batch = audios_to_verify[i : i + batch_size]
            batch_index = i // batch_size
            batch_response = self._evaluation_service.verify_files(
                evaluation_id,
                batch,
                timeout=self._eval_config.verify_timeout,
                context={
                    "batch_index": batch_index,
                    "batch_size": len(batch),
                    "batch_start": i,
                    "total_files": len(audios_to_verify),
                },
            )

            if self._upload_ledger is None:
                all_results.extend(batch_response.results)
            else:
                all_results.extend(
                    self._persist_verify_results(evaluation_id, batch_response.results)
                )
            total_verified += batch_response.verified_count
            total_failed += batch_response.failed_count

        return VerifyFilesResponse(
            all_verified=(total_failed == 0),
            verified_count=total_verified,
            failed_count=total_failed,
            results=all_results,
        )

    def _get_failed_audios(
        self, audios: List[Audio], failed_results: List
    ) -> List[Audio]:
        failed_names = {r.uploaded_file_name for r in failed_results}
        return [a for a in audios if a.remote_object_name in failed_names]

    def _get_ledger_row(self, audio: Audio) -> Optional[UploadLedgerRow]:
        if self._upload_ledger is None:
            return None
        return self._upload_ledger.get(self.get_evaluation_id(), audio.remote_object_name)

    def _should_skip_upload(self, audio: Audio) -> bool:
        if self._upload_ledger is None:
            return False

        file_index = self._assign_file_index(audio)
        manifest_key = self._build_current_manifest_key(audio)
        row = self._upload_ledger.upsert_queued_file(
            self.get_evaluation_id(),
            audio.remote_object_name,
            audio.path,
            file_index=file_index,
            manifest_key=manifest_key,
        )
        self._apply_ledger_remote_identity(audio, row)
        if not self._ledger_row_matches_local_file(audio, row):
            if row.status in {"metadata_registering", "metadata_registered", "verified"}:
                raise ValueError(
                    "Upload ledger row does not match the current local file for "
                    "the current upload item. Start a fresh evaluation or remove the stale "
                    "ledger row before resuming."
                )
            row = self._upload_ledger.reset_for_reupload(
                self.get_evaluation_id(), row.remote_object_name, audio.path
            )
        self._hydrate_audio_from_ledger(audio, row)
        return row.status in {
            "uploaded",
            "metadata_registering",
            "metadata_registered",
            "verified",
        }

    def _assign_file_index(self, audio: Audio) -> int:
        existing = getattr(audio, "_podonos_file_index", None)
        if existing is not None:
            return int(existing)
        file_index = self._next_file_index
        setattr(audio, "_podonos_file_index", file_index)
        self._next_file_index += 1
        return file_index

    def _apply_ledger_remote_identity(
        self, audio: Audio, row: UploadLedgerRow
    ) -> None:
        if audio.remote_object_name == row.remote_object_name:
            return
        setattr(audio, "_remote_object_name", row.remote_object_name)

    def _build_current_manifest_key(self, audio: Audio) -> str:
        content_md5, file_size = calculate_file_md5_base64(audio.path)
        audio.set_integrity_info(content_md5, file_size)
        return build_upload_manifest_key(
            audio.to_create_file_dict(), content_md5, file_size
        )

    def _ledger_row_matches_local_file(
        self, audio: Audio, row: UploadLedgerRow
    ) -> bool:
        if row.status == "queued":
            return os.path.abspath(row.local_path) == os.path.abspath(audio.path)
        if os.path.abspath(row.local_path) != os.path.abspath(audio.path):
            return False
        if not row.content_md5 or not row.file_size:
            return row.status == "upload_failed"

        content_md5, file_size = calculate_file_md5_base64(audio.path)
        if content_md5 != row.content_md5 or file_size != row.file_size:
            return False
        audio.set_integrity_info(content_md5, file_size)
        if row.status != "upload_failed":
            manifest_hash = build_upload_manifest_hash(
                audio.to_create_file_dict(), content_md5, file_size
            )
            if row.manifest_hash != manifest_hash:
                return False
        return True

    def _get_audios_needing_metadata_registration(
        self, audios: List[Audio]
    ) -> List[Audio]:
        if self._upload_ledger is None:
            return audios

        audios_for_metadata: List[Audio] = []
        for audio in audios:
            row = self._get_ledger_row(audio)
            if row is None:
                audios_for_metadata.append(audio)
                continue
            self._hydrate_audio_from_ledger(audio, row)
            if row.status == "uploaded":
                audios_for_metadata.append(audio)
        return audios_for_metadata

    def _get_audios_needing_verification(self, audios: List[Audio]) -> List[Audio]:
        if self._upload_ledger is None:
            return audios

        audios_for_verification: List[Audio] = []
        for audio in audios:
            row = self._get_ledger_row(audio)
            if row is None:
                audios_for_verification.append(audio)
                continue
            self._hydrate_audio_from_ledger(audio, row)
            if row.status in {"metadata_registering", "metadata_registered", "verify_failed"}:
                audios_for_verification.append(audio)
        return audios_for_verification

    def _register_metadata_for_audios(self, audios: List[Audio]) -> None:
        if self._upload_ledger is None:
            for i in range(0, len(audios), 500):
                batch = audios[i : i + 500]
                self._evaluation_service.create_evaluation_files(
                    self.get_evaluation_id(),
                    batch,
                    timeout=self._eval_config.api_timeout,
                    context={
                        "batch_index": i // 500,
                        "batch_size": len(batch),
                        "batch_start": i,
                        "total_files": len(audios),
                    },
                )
            return

        for i in range(0, len(audios), 500):
            batch = audios[i : i + 500]
            batch_to_register: List[Audio] = []
            ledger_batch_to_mark_registered: List[Audio] = []
            for audio in batch:
                row = self._get_ledger_row(audio)
                if row is None:
                    batch_to_register.append(audio)
                    continue
                if row.status == "uploaded":
                    self._upload_ledger.mark_metadata_registering(
                        self.get_evaluation_id(), audio.remote_object_name
                    )
                    batch_to_register.append(audio)
                    ledger_batch_to_mark_registered.append(audio)

            if not batch_to_register:
                continue

            try:
                self._evaluation_service.create_evaluation_files(
                    self.get_evaluation_id(),
                    batch_to_register,
                    timeout=self._eval_config.api_timeout,
                    context={
                        "batch_index": i // 500,
                        "batch_size": len(batch_to_register),
                        "batch_start": i,
                        "total_files": len(audios),
                    },
                )
            except Exception as exc:
                for audio in ledger_batch_to_mark_registered:
                    try:
                        self._upload_ledger.mark_metadata_registration_retry_needed(
                            self.get_evaluation_id(),
                            audio.remote_object_name,
                            type(exc).__name__,
                            redact_secrets(exc),
                        )
                    except Exception as ledger_exc:
                        log.warning(
                            "Failed to roll back metadata registration state for "
                            f"{audio.remote_object_name}: {redact_secrets(ledger_exc)}"
                        )
                raise
            for audio in ledger_batch_to_mark_registered:
                self._upload_ledger.mark_metadata_registered(
                    self.get_evaluation_id(), audio.remote_object_name
                )

    def _persist_verify_results(
        self, evaluation_id: str, results: List[FileVerificationResult]
    ) -> List[FileVerificationResult]:
        if self._upload_ledger is None:
            return results

        failed_results: List[FileVerificationResult] = []
        for result in results:
            try:
                if result.verified:
                    self._upload_ledger.mark_verified(
                        evaluation_id, result.uploaded_file_name
                    )
                else:
                    existing = self._upload_ledger.get(
                        evaluation_id, result.uploaded_file_name
                    )
                    error_type = result.error.code if result.error else "VERIFY_FAILED"
                    error_message = (
                        result.error.message if result.error else "Verification failed"
                    )
                    if existing and existing.status == "metadata_registering":
                        self._upload_ledger.mark_metadata_registration_retry_needed(
                            evaluation_id,
                            result.uploaded_file_name,
                            error_type,
                            error_message,
                        )
                    else:
                        self._upload_ledger.mark_verify_failed(
                            evaluation_id,
                            result.uploaded_file_name,
                            error_type,
                            error_message,
                        )
                    failed_results.append(result)
            except Exception as exc:
                log.warning(
                    f"Failed to persist upload ledger verification result for "
                    f"{result.uploaded_file_name}: {redact_secrets(exc)}"
                )
                if not result.verified:
                    failed_results.append(result)
        return failed_results

    def _hydrate_audio_from_ledger(self, audio: Audio, row: UploadLedgerRow) -> None:
        if row.content_md5 and row.file_size:
            try:
                audio.set_integrity_info(row.content_md5, row.file_size)
            except Exception as exc:
                log.warning(
                    f"Failed to hydrate integrity info from upload ledger for "
                    f"{row.remote_object_name}: {redact_secrets(exc)}"
                )
        if row.upload_start_at and row.upload_finish_at:
            try:
                audio.set_upload_at(row.upload_start_at, row.upload_finish_at)
            except Exception as exc:
                log.warning(
                    f"Failed to hydrate upload times from upload ledger for "
                    f"{row.remote_object_name}: {redact_secrets(exc)}"
                )

    def _retry_failed_uploads(self, failed_audios: List[Audio]) -> None:
        metadata_retry_audios: List[Audio] = []
        upload_retry_audios: List[Audio] = []

        for audio in failed_audios:
            row = self._get_ledger_row(audio)
            if self._upload_ledger is not None and row and row.status == "uploaded":
                metadata_retry_audios.append(audio)
            else:
                upload_retry_audios.append(audio)

        if metadata_retry_audios:
            log.info(
                f"Retrying metadata registration for "
                f"{len(metadata_retry_audios)} file(s)..."
            )
            self._register_metadata_for_audios(metadata_retry_audios)

        if not upload_retry_audios:
            return

        log.info(f"Re-uploading {len(upload_retry_audios)} failed files...")

        retry_manager = UploadManager(
            evaluation_service=self._evaluation_service,
            max_workers=min(len(upload_retry_audios), self._eval_config.max_upload_workers),
            api_timeout=self._eval_config.api_timeout,
            upload_timeout=self._eval_config.upload_timeout,
            upload_ledger=self._upload_ledger,
        )

        for audio in upload_retry_audios:
            retry_manager.add_file_to_queue(self.get_evaluation_id(), audio)

        retry_manager.wait_and_close()
        self._register_metadata_for_audios(upload_retry_audios)

    def _find_original_name(self, remote_object_name: str) -> str:
        for group in self._ordered_file_groups:
            for audio in group.audios:
                if audio.remote_object_name == remote_object_name:
                    return os.path.basename(audio.path)
        return remote_object_name

    def _process_upload_times(self) -> None:
        """Process and store upload times for audio files."""
        if not self._upload_manager:
            return

        upload_start, upload_finish = self._upload_manager.get_upload_time()
        for group in self._ordered_file_groups:
            for audio in group.audios:
                self._update_audio_upload_times(audio, upload_start, upload_finish)

    @validate_args(
        audio=Rules.instance_of(Audio),
        upload_start=Rules.dict_not_none,
        upload_finish=Rules.dict_not_none,
    )
    def _update_audio_upload_times(
        self, audio: Audio, upload_start: Dict[str, str], upload_finish: Dict[str, str]
    ) -> None:
        """Update upload times for a single audio file.

        Args:
            audio: Audio object to update
            upload_start: Dictionary of upload start times
            upload_finish: Dictionary of upload finish times
        """
        remote_object_name = audio.remote_object_name
        upload_start_at = upload_start[remote_object_name]
        upload_finish_at = upload_finish[remote_object_name]
        audio.set_upload_at(upload_start_at, upload_finish_at)

    def _upload_session_json(self) -> None:
        """Upload the session JSON data."""
        session_json_hash = self._finalization_hash(self._session_json_payload())
        if self._upload_ledger is not None and self._upload_ledger.is_session_json_uploaded(
            self.get_evaluation_id(), session_json_hash
        ):
            log.info("Skipping session JSON upload; upload ledger marks it complete.")
            return
        self._evaluation_service.upload_session_json(
            self.get_evaluation_id(), self._eval_config, self._ordered_file_groups
        )
        if self._upload_ledger is not None:
            self._upload_ledger.mark_session_json_uploaded(
                self.get_evaluation_id(), session_json_hash
            )

    def _session_json_payload(self) -> Dict[str, Any]:
        session_json = self._eval_config.to_dict()
        session_json["files"] = [group.to_dict() for group in self._ordered_file_groups]
        return session_json

    def _finalization_hash(self, payload: Dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _cleanup(self) -> None:
        """Clean up the evaluation session."""
        self._initialized = False
        self._ordered_file_groups = []

    @validate_args(eval_config=Rules.instance_of(EvalConfig))
    def _set_evaluation(self, eval_config: EvalConfig) -> EvaluationEntity:
        if eval_config.resume_evaluation_id:
            evaluation = self._evaluation_service.get_evaluation(
                eval_config.resume_evaluation_id,
                timeout=eval_config.api_timeout,
                context={"operation": "resume_evaluation"},
            )
            if evaluation.batch_size != eval_config.eval_batch_size:
                raise ValueError(
                    "Backend evaluation batch_size does not match the upload "
                    "ledger contract: "
                    f"backend={evaluation.batch_size}, "
                    f"ledger={eval_config.eval_batch_size}."
                )
            eval_config.eval_id = evaluation.id
            return evaluation
        if eval_config.eval_template_id:
            return self._evaluation_service.create_from_template(eval_config)
        return self._evaluation_service.create(eval_config)

    @validate_args(evaluation_id=Rules.str_non_empty, audio=Rules.instance_of(Audio))
    def _upload_one_file(self, evaluation_id: str, audio: Audio) -> None:
        log.debug("Adding file to upload queue")
        if not self._eval_config:
            raise ValueError("No evaluation session is open.")

        if self._upload_manager is None:
            log.debug(f"max_upload_workers: {self._eval_config.max_upload_workers}")
            self._upload_manager = UploadManager(
                evaluation_service=self._evaluation_service,
                max_workers=self._eval_config.max_upload_workers,
                api_timeout=self._eval_config.api_timeout,
                upload_timeout=self._eval_config.upload_timeout,
                upload_ledger=self._upload_ledger,
            )

        if self._upload_manager:
            if self._should_skip_upload(audio):
                log.info(
                    f"Skipping upload for {audio.remote_object_name}; "
                    "upload ledger already has completed upload state."
                )
                return
            self._upload_manager.add_file_to_queue(evaluation_id, audio)

    def _update_ranking_batch_size_before_upload(self) -> None:
        """Adjust batch_size for RANKING to match the group size (N) before uploads/metadata."""
        if not self._ordered_file_groups or not self._ordered_file_groups[0].audios:
            raise ValueError(
                "RANKING requires at least one group with files before closing the session"
            )
        group_size = len(self._ordered_file_groups[0].audios)
        if group_size < 2:
            raise ValueError("RANKING requires at least two files per group")

        if self._eval_config.resume_evaluation_id:
            expected_size = self._eval_config.eval_batch_size
            if group_size != expected_size:
                raise ValueError(
                    "Resumed RANKING evaluation group size does not match the "
                    f"original evaluation contract: expected {expected_size}, "
                    f"got {group_size}."
                )
            return

        payload: Dict[str, Any] = {
            "id": self.get_evaluation_id(),
            "language": self._eval_config.eval_language.value,
            "build_process": "FILE_UPLOAD",
            "evaluation_type": self._eval_config.eval_type.get_type(),
            "batch_size": group_size,
            "meta_data": {},
        }
        self._evaluation_service.update_specific_fields(
            self.get_evaluation_id(),
            payload,
            timeout=self._eval_config.api_timeout,
            context={
                "operation": "ranking_batch_size_resolution",
                "batch_size": group_size,
            },
        )
        self._eval_config.eval_batch_size = group_size
