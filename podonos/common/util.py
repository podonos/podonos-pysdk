import base64
import hashlib
import os
import time
import uuid
from typing import Tuple

from podonos.core.base import log


def generate_random_name():
    current_time_milliseconds = int(time.time() * 1000)
    random_uuid = uuid.uuid4()
    return f"{current_time_milliseconds}-{random_uuid}"


def generate_random_group_name():
    current_time_milliseconds = int(time.time() * 1000)
    random_uuid = uuid.uuid4()
    return f"{current_time_milliseconds}_{random_uuid}"


def process_paths_to_posix(original_path: str, remote_object_path: str) -> Tuple[str, str]:
    """Convert paths to POSIX style

    Args:
        original_path: Original file path
        remote_object_path: Remote object path

    Returns:
        Tuple of processed original and remote paths
    """
    return (original_path.replace("\\", "/"), remote_object_path.replace("\\", "/"))


def get_content_type_by_filename(path: str) -> str:
    log.check_notnone(path)
    log.check_ne(path, "")

    _, ext = os.path.splitext(path)
    if ext == ".wav":
        return "audio/wav"
    elif ext == ".mp3":
        return "audio/mpeg"
    elif ext == ".flac":
        return "audio/flac"
    elif ext == ".json":
        return "application/json"
    return "application/octet-stream"


def calculate_file_md5_base64(file_path: str) -> Tuple[str, int]:
    """Calculate MD5 hash (base64 encoded) and file size for upload integrity verification.

    This function reads the file in chunks to efficiently handle large files
    and returns both the MD5 hash (base64 encoded, 24 characters) and file size.

    Args:
        file_path: Path to the file to calculate MD5 for.

    Returns:
        Tuple of (md5_base64_string, file_size_bytes).
        - md5_base64_string: Base64 encoded MD5 hash (24 characters).
        - file_size_bytes: File size in bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If the file cannot be read.

    Example:
        >>> md5_hash, size = calculate_file_md5_base64("/path/to/audio.wav")
        >>> print(f"MD5: {md5_hash}, Size: {size} bytes")
        MD5: AA259hLYqLX6hjV81ve5Cg==, Size: 1048576 bytes
    """
    log.check_notnone(file_path)
    log.check_ne(file_path, "")

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = os.path.getsize(file_path)
    md5_hash = hashlib.md5(usedforsecurity=False)

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5_hash.update(chunk)

    md5_base64 = base64.b64encode(md5_hash.digest()).decode("utf-8")
    return md5_base64, file_size
