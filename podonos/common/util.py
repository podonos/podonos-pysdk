import time
from typing import Tuple
import uuid


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
