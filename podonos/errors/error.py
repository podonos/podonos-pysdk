from dataclasses import dataclass
from typing import List, Optional

from podonos.common.redaction import redact_secrets


class NotSupportedError(Exception):
    """Exception raised for unsupported operations."""

    def __init__(self, message: str = "This operation is not supported"):
        self.message = message
        super().__init__(self.message)


class InvalidFileError(Exception):
    """Exception raised for invalid file input."""

    def __init__(self, message: str = "This file is invalid"):
        self.message = message
        super().__init__(self.message)


@dataclass
class FileVerificationFailure:
    uploaded_file_name: str
    original_name: str
    error_code: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None


class UploadVerificationError(Exception):
    """Raised when file upload verification fails."""

    def __init__(
        self,
        message: str,
        failures: List[FileVerificationFailure],
        retry_count: int = 0,
        max_retries: int = 3,
    ):
        self.failures = failures
        self.retry_count = retry_count
        self.max_retries = max_retries

        detail_lines = [
            f"\n  - {redact_secrets(f.original_name)}: {redact_secrets(f.error_code)} "
            f"({redact_secrets(f.message)})"
            for f in failures
        ]
        full_message = f"{message}{''.join(detail_lines)}"
        super().__init__(full_message)


class UploadRetryExhaustedError(UploadVerificationError):
    """Raised when max retry attempts exceeded for upload verification."""

    pass


@dataclass
class UploadFailure:
    path: str
    remote_object_name: str
    error_type: str
    error_message: str


class UploadBatchError(Exception):
    """Raised when one or more concurrent uploads fail."""

    def __init__(self, failures: List[UploadFailure]):
        self.failures = failures
        detail_lines = [
            f"\n  - upload item ({redact_secrets(failure.remote_object_name)}): "
            f"{redact_secrets(failure.error_type)}: "
            f"{redact_secrets(failure.error_message)}"
            for failure in failures
        ]
        super().__init__(
            f"{len(failures)} upload(s) failed:{''.join(detail_lines)}"
        )
