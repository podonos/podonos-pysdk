from dataclasses import dataclass
from typing import List, Optional


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
            f"\n  - {f.original_name}: {f.error_code} ({f.message})" for f in failures
        ]
        full_message = f"{message}{''.join(detail_lines)}"
        super().__init__(full_message)


class UploadRetryExhaustedError(UploadVerificationError):
    """Raised when max retry attempts exceeded for upload verification."""

    pass
