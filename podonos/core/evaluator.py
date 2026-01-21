from typing import Dict, List, Optional

from podonos.common.enum import EvalType
from podonos.common.validator import Rules, validate_args
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig
from podonos.core.file import Audio, AudioGroup, File, FileTransformer, FileValidator
from podonos.core.upload_manager import UploadManager
from podonos.entity.evaluation import EvaluationEntity
from podonos.entity.verification import FileVerificationResult, VerifyFilesResponse
from podonos.errors.error import FileVerificationFailure, UploadRetryExhaustedError
from podonos.service.evaluation_service import EvaluationService

MAX_UPLOAD_RETRIES = 3
DEFAULT_VERIFY_BATCH_SIZE = 500  # Default batch size, can be overridden via EvalConfig


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
    _ordered_file_groups: List[AudioGroup]  # ordered evaluation files groups

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
        self._evaluation = self._set_evaluation(eval_config)
        self._file_transformer = FileTransformer(eval_config)
        self._file_validator = FileValidator(eval_config)
        self._supported_eval_types = supported_eval_types
        self._ordered_file_groups = []
        self._upload_manager = None

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

        files = self._file_validator.validate_files([file0, file1, file2])
        audio_group = self._file_transformer.transform_into_audio_group(files)
        self._ordered_file_groups.append(audio_group)
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

        for i in range(0, len(all_audios), 500):
            batch = all_audios[i : i + 500]
            self._evaluation_service.create_evaluation_files(
                self.get_evaluation_id(), batch
            )

        log.info(f"Verifying {len(all_audios)} files...")
        verify_response = self._verify_files_in_batches(
            self.get_evaluation_id(), all_audios
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

        log.info("Triggering file processing...")
        process_response = self._evaluation_service.process_files(
            self.get_evaluation_id()
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

        batch_size = self._eval_config.verify_batch_size

        for i in range(0, len(audios), batch_size):
            batch = audios[i : i + batch_size]
            batch_response = self._evaluation_service.verify_files(evaluation_id, batch)

            all_results.extend(batch_response.results)
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

    def _retry_failed_uploads(self, failed_audios: List[Audio]) -> None:
        log.info(f"Re-uploading {len(failed_audios)} failed files...")

        retry_manager = UploadManager(
            evaluation_service=self._evaluation_service,
            max_workers=min(len(failed_audios), self._eval_config.max_upload_workers),
        )

        for audio in failed_audios:
            retry_manager.add_file_to_queue(self.get_evaluation_id(), audio)

        retry_manager.wait_and_close()

        for i in range(0, len(failed_audios), 500):
            batch = failed_audios[i : i + 500]
            self._evaluation_service.create_evaluation_files(
                self.get_evaluation_id(), batch
            )

    def _find_original_name(self, remote_object_name: str) -> str:
        for group in self._ordered_file_groups:
            for audio in group.audios:
                if audio.remote_object_name == remote_object_name:
                    return audio.path
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
        self._evaluation_service.upload_session_json(
            self.get_evaluation_id(), self._eval_config, self._ordered_file_groups
        )

    def _cleanup(self) -> None:
        """Clean up the evaluation session."""
        self._initialized = False
        self._ordered_file_groups = []

    @validate_args(eval_config=Rules.instance_of(EvalConfig))
    def _set_evaluation(self, eval_config: EvalConfig) -> EvaluationEntity:
        if eval_config.eval_template_id:
            return self._evaluation_service.create_from_template(eval_config)
        return self._evaluation_service.create(eval_config)

    @validate_args(evaluation_id=Rules.str_non_empty, audio=Rules.instance_of(Audio))
    def _upload_one_file(self, evaluation_id: str, audio: Audio) -> None:
        log.debug(f"Adding to queue: {audio.path}")
        if not self._eval_config:
            raise ValueError("No evaluation session is open.")

        if self._upload_manager is None:
            log.debug(f"max_upload_workers: {self._eval_config.max_upload_workers}")
            self._upload_manager = UploadManager(
                evaluation_service=self._evaluation_service,
                max_workers=self._eval_config.max_upload_workers,
            )

        if self._upload_manager:
            self._upload_manager.add_file_to_queue(evaluation_id, audio)
