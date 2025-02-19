from typing import Dict, List, Optional


from podonos.common.enum import EvalType
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.config import EvalConfig
from podonos.core.file import File, Audio, AudioGroup, FileTransformer, FileValidator
from podonos.core.upload_manager import UploadManager
from podonos.entity.evaluation import EvaluationEntity
from podonos.service.evaluation_service import EvaluationService


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
    _upload_manager: Optional[UploadManager] = None  # Upload manager. Lazy initialization when used for saving resources.
    _ordered_file_groups: List[AudioGroup]  # ordered evaluation files groups

    def __init__(self, api_client: APIClient, eval_config: EvalConfig, supported_eval_types: List[EvalType]):
        """Initialize the evaluator.

        Args:
            api_client: API client for making requests
            eval_config: Optional evaluation configuration
        """
        self._initialized = True
        self._validate_initialization(api_client, eval_config, supported_eval_types)
        self._initialize_attributes(api_client, eval_config, supported_eval_types)

    def _validate_initialization(self, api_client: APIClient, eval_config: EvalConfig, supported_eval_types: List[EvalType]) -> None:
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

    def _initialize_attributes(self, api_client: APIClient, eval_config: EvalConfig, supported_eval_types: List[EvalType]) -> None:
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

    def _validate_eval_type(self, method_name: str) -> None:
        """Validate if the evaluation type is supported for the given method.

        Args:
            method_name: Name of the method being validated ('add_file' or 'add_files')

        Raises:
            ValueError: If evaluation type is not supported for the method
        """
        if method_name == "add_file":
            supported_types = [EvalType.NMOS, EvalType.QMOS, EvalType.P808, EvalType.CUSTOM_SINGLE]
            error_msg = f"The '{method_name}' is only supported for single file evaluation types: " f"{supported_types}"
        else:  # add_files
            supported_types = [EvalType.CMOS, EvalType.DMOS, EvalType.PREF, EvalType.SMOS, EvalType.CSMOS, EvalType.CUSTOM_DOUBLE]
            error_msg = f"The '{method_name}' is only supported for comparison evaluation types: " f"{supported_types}"

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
        """Close the evaluation session and upload results.

        Returns:
            Dict[str, str]: Status of the operation

        Raises:
            ValueError: If session is not initialized or upload manager is not defined
        """
        self._validate_close()
        self._wait_for_uploads()
        self._process_audio_files()
        self._upload_session_json()
        self._cleanup()
        return {"status": "ok"}

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
            evaluation_id=self.get_evaluation_id(), remote_object_name=audio_group.audios[0].remote_object_name, path=audio_group.audios[0].path
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
            self._upload_one_file(evaluation_id=self.get_evaluation_id(), remote_object_name=audio.remote_object_name, path=audio.path)

    def _validate_close(self) -> None:
        """Validate the state before closing.

        Raises:
            ValueError: If session is not properly initialized
        """
        if not self._initialized or self._eval_config is None:
            raise ValueError("No evaluation session is open.")

    def _wait_for_uploads(self) -> None:
        """Wait for all file uploads to complete."""
        log.debug("Wait until the upload manager shuts down all the upload workers")
        assert self._upload_manager and self._upload_manager.wait_and_close()

    def _process_audio_files(self) -> None:
        """Process and upload audio files metadata."""
        log.info("Uploading the final pieces...")
        audios = [audio for group in self._ordered_file_groups for audio in group.audios]
        for i in range(0, len(audios), 500):
            self._evaluation_service.create_evaluation_files(self.get_evaluation_id(), audios[i : i + 500])

        self._process_upload_times()

    def _process_upload_times(self) -> None:
        """Process and store upload times for audio files."""
        if not self._upload_manager:
            return

        upload_start, upload_finish = self._upload_manager.get_upload_time()
        for group in self._ordered_file_groups:
            for audio in group.audios:
                self._update_audio_upload_times(audio, upload_start, upload_finish)

    def _update_audio_upload_times(self, audio: Audio, upload_start: Dict[str, str], upload_finish: Dict[str, str]) -> None:
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
        self._evaluation_service.upload_session_json(self.get_evaluation_id(), self._eval_config, self._ordered_file_groups)

    def _cleanup(self) -> None:
        """Clean up the evaluation session."""
        self._initialized = False
        self._ordered_file_groups = []

    def _set_evaluation(self, eval_config: EvalConfig) -> EvaluationEntity:
        if eval_config.eval_template_id:
            return self._evaluation_service.create_from_template(eval_config)
        return self._evaluation_service.create(eval_config)

    def _upload_one_file(
        self,
        evaluation_id: str,
        remote_object_name: str,
        path: str,
    ) -> None:
        """
        Start uploading one file to server.

        Args:
            evaluation_id: New evaluation's id.
            remote_object_name: Path to the remote file name.
            path: Path to the local file.
        Returns:
            None
        """
        log.check_notnone(evaluation_id)
        log.check_notnone(remote_object_name)
        log.check_notnone(path)
        log.check_ne(evaluation_id, "")
        log.check_ne(remote_object_name, "")
        log.check_ne(path, "")

        # Get the presigned URL for one file
        log.debug(f"Adding to queue: {path}")
        if not self._eval_config:
            raise ValueError("No evaluation session is open.")

        # Lazy initialization of upload manager.
        if self._upload_manager is None:
            log.debug(f"max_upload_workers: {self._eval_config.max_upload_workers}")
            self._upload_manager = UploadManager(
                evaluation_service=self._evaluation_service,
                max_workers=self._eval_config.max_upload_workers,
            )

        if self._upload_manager:
            self._upload_manager.add_file_to_queue(evaluation_id, remote_object_name, path)
        return
