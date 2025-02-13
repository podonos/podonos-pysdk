from dataclasses import dataclass
from datetime import datetime
import os
import soundfile as sf
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from podonos.common.enum import QuestionFileType
from podonos.common.util import generate_random_name, process_paths_to_posix
from podonos.core.base import *
from podonos.core.file import File


class AudioMeta:
    _nchannels: int
    _framerate: int
    _duration_in_ms: int

    def __init__(self, path: str) -> None:
        log.check_notnone(path)
        self._nchannels, self._framerate, self._duration_in_ms = self._set_audio_meta(path)
        log.check_ge(self._nchannels, 0)
        log.check_ge(self._framerate, 0)
        log.check_ge(self._duration_in_ms, 0)

    @property
    def nchannels(self) -> int:
        return self._nchannels

    @property
    def framerate(self) -> int:
        return self._framerate

    @property
    def duration_in_ms(self) -> int:
        return self._duration_in_ms

    def _set_audio_meta(self, path: str) -> Tuple[int, int, int]:
        """Gets info from an audio file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
            AssertionError: if the file format is not wav.
        """
        log.check_notnone(path)
        log.check_ne(path, "")
        log.check(os.path.isfile(path), f"{path} doesn't exist")
        log.check(os.access(path, os.R_OK), f"{path} isn't readable")

        # Check if this is wav or mp3.
        suffix = Path(path).suffix
        support_file_type = [".wav", ".mp3", ".flac"]
        assert suffix in support_file_type, f"Unsupported file format: {path}. It must be wav, mp3, or flac."
        if suffix in support_file_type:
            return self._get_audio_info(path)
        return 0, 0, 0

    def _get_audio_info(self, filepath: str) -> Tuple[int, int, int]:
        """Gets info from a wave file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
        """
        try:
            log.check_notnone(filepath)
            log.check_ne(filepath, "")

            f = sf.SoundFile(filepath)
            nframes = f.frames
            nchannels = f.channels
            framerate = f.samplerate
            log.check_gt(nframes, 0)
            log.check_gt(nchannels, 0)
            log.check_gt(framerate, 0)

            duration_in_ms = int(nframes * 1000.0 / float(framerate))
            log.check_gt(duration_in_ms, 0)
            return nchannels, framerate, duration_in_ms
        except AttributeError as e:
            log.error(f"Attribute error while getting audio info: {e}")
            return 0, 0, 0
        except Exception as e:
            log.error(f"Error getting audio info: {e}")
            return 0, 0, 0


class Audio(File):
    def __init__(
        self,
        path: str,
        name: str,
        remote_object_name: str,
        script: Optional[str],
        tags: List[str],
        model_tag: str,
        is_ref: bool,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
    ):
        super().__init__(path, model_tag, tags, script, is_ref)
        self._name = name
        self._remote_object_name = remote_object_name
        self._group = group
        self._type = type
        self._metadata = AudioMeta(path)
        self._order_in_group = order_in_group
        self._upload_start_at = None
        self._upload_finish_at = None

    @classmethod
    def from_file(
        cls,
        file: File,
        creation_timestamp: str,
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
    ) -> "Audio":
        """Create Audio instance from File object

        Args:
            file: Source File object
            creation_timestamp: Timestamp for remote path
            group: Optional group identifier
            type: Question file type
            order_in_group: Order in group

        Returns:
            New Audio instance
        """
        remote_object_name = os.path.join(creation_timestamp, generate_random_name())
        original_path, remote_path = process_paths_to_posix(file.path, str(remote_object_name))

        return cls(
            path=file.path,
            name=original_path,
            remote_object_name=remote_path,
            script=file.script,
            tags=file.tags,
            model_tag=file.model_tag,
            is_ref=file.is_ref if file.is_ref else False,
            group=group,
            type=type,
            order_in_group=order_in_group,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def remote_object_name(self) -> str:
        return self._remote_object_name

    @property
    def group(self) -> Optional[str]:
        return self._group

    @property
    def type(self) -> QuestionFileType:
        return self._type

    @property
    def order_in_group(self) -> int:
        return self._order_in_group

    def set_upload_at(self, start_at: str, finish_at: str) -> None:
        log.check_notnone(start_at)
        log.check_notnone(finish_at)
        log.check_ne(start_at, "")
        log.check_ne(finish_at, "")

        self._upload_start_at = start_at
        self._upload_finish_at = finish_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self._name,
            "remote_name": self._remote_object_name,
            "nchannels": self._metadata.nchannels,
            "framerate": self._metadata.framerate,
            "duration_in_ms": self._metadata.duration_in_ms,
            "upload_start_at": self._upload_start_at,
            "upload_finish_at": self._upload_finish_at,
            "model_tag": self._model_tag,
            "is_ref": self._is_ref,
            "tag": self._tags,
            "type": self._type,
            "script": self._script,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }

    def to_create_file_dict(self) -> Dict[str, Any]:
        return {
            "original_name": self._path,
            "uploaded_file_name": self._remote_object_name,
            "duration": self._metadata.duration_in_ms,
            "model_tag": self._model_tag,
            "is_ref": self._is_ref,
            "tags": self._tags,
            "type": self._type,
            "script": self._script,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }


@dataclass
class AudioGroup:
    """Represent a group of files for evaluation"""

    group_id: Optional[str]  # None for single stimulus, UUID for double stimuli
    audios: List[Audio]
    created_at: datetime

    def __init__(self, group_id: Optional[str], audios: List[Audio], created_at: datetime):
        self.group_id = group_id
        self.created_at = created_at
        self.audios = self.set_audios(audios)

    def set_audios(self, audios: List[Audio]):
        """
        Args:
            audios: List of Audio objects

        Raises:
            ValueError: If all audios don't have the same group_id or order_in_group is not unique
        """
        for i, audio in enumerate(audios):
            if audio.group != self.group_id:
                raise ValueError(f"All audios must have the same group_id. Expected {self.group_id}, got {audio.group}.")
            if audio.order_in_group != i:
                raise ValueError(f"Order in group must be unique. Got {audio.order_in_group}.")

        return audios

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "audios": [audio.to_dict() for audio in self.audios],
            "created_at": self.created_at.isoformat(),
        }
