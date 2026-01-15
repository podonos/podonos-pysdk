from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class VerificationErrorDetail:
    code: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    @classmethod
    def from_dict(
        cls, data: Optional[Dict[str, Any]]
    ) -> Optional["VerificationErrorDetail"]:
        if data is None:
            return None
        return cls(
            code=data.get("code", ""),
            message=data.get("message", ""),
            expected=data.get("expected"),
            actual=data.get("actual"),
        )


@dataclass
class FileVerificationResult:
    uploaded_file_name: str
    verified: bool
    file_meta_id: Optional[str]
    error: Optional[VerificationErrorDetail]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileVerificationResult":
        return cls(
            uploaded_file_name=data["uploaded_file_name"],
            verified=data["verified"],
            file_meta_id=data.get("file_meta_id"),
            error=VerificationErrorDetail.from_dict(data.get("error")),
        )


@dataclass
class VerifyFilesResponse:
    all_verified: bool
    verified_count: int
    failed_count: int
    results: List[FileVerificationResult]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerifyFilesResponse":
        return cls(
            all_verified=data["all_verified"],
            verified_count=data["verified_count"],
            failed_count=data["failed_count"],
            results=[FileVerificationResult.from_dict(r) for r in data["results"]],
        )


@dataclass
class ProcessFilesResponse:
    processing_count: int
    file_meta_ids: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessFilesResponse":
        return cls(
            processing_count=data["processing_count"],
            file_meta_ids=data["file_meta_ids"],
        )
