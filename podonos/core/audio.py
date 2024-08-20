import soundfile as sf
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from podonos.common.enum import QuestionFileType
from podonos.errors.error import InvalidFileError


class AudioMeta:
    _nchannels: int
    _framerate: int
    _duration_in_ms: int

    def __init__(self, path: str) -> None:
        self._nchannels, self._framerate, self._duration_in_ms = self._set_audio_meta(path)

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

        # Check if this is wav or mp3.
        suffix = Path(path).suffix
        assert suffix in [
            ".wav",
            ".mp3",
        ], f"Unsupported file format: {path}. It must be wav or mp3."
        if suffix == ".wav":
            return self._get_wave_info(path)
        elif suffix == ".mp3":
            return self._get_mp3_info(path)
        return 0, 0, 0

    def _get_wave_info(self, filepath: str) -> Tuple[int, int, int]:
        """Gets info from a wave file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
        """

        f = sf.SoundFile(filepath)
        nframes = f.frames
        nchannels = f.channels
        framerate = f.samplerate
        if framerate == 0:
            raise InvalidFileError()

        duration_in_ms = int(nframes * 1000.0 / float(framerate))
        return nchannels, framerate, duration_in_ms

    def _get_mp3_info(self, filepath: str) -> Tuple[int, int, int]:
        """Gets info from a mp3 file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
        """
        f = sf.SoundFile(filepath)
        nframes = f.frames
        nchannels = f.channels
        framerate = f.samplerate
        if framerate == 0:
            raise InvalidFileError()

        duration_in_ms = int(nframes * 1000.0 / float(framerate))
        return nchannels, framerate, duration_in_ms


class Audio:
    _path: str
    _name: str
    _remote_object_name: str
    _metadata: AudioMeta
    _script: Optional[str] = None
    _upload_start_at: Optional[str] = None
    _upload_finish_at: Optional[str] = None
    _tags: Optional[List[str]] = None
    _group: Optional[str] = None
    _type: QuestionFileType = QuestionFileType.STIMULUS
    _order_in_group: int = 0

    def __init__(
        self,
        path: str,
        name: str,
        remote_object_name: str,
        script: Optional[str],
        tags: Optional[List[str]],
        group: Optional[str],
        type: QuestionFileType,
        order_in_group: int,
    ) -> None:
        self._path = path
        self._name = name
        self._remote_object_name = remote_object_name
        self._script = script
        self._metadata = AudioMeta(path)
        self._tags = tags
        self._group = group
        self._type = type
        self._order_in_group = order_in_group

    @property
    def path(self) -> str:
        return self._path

    @property
    def name(self) -> str:
        return self._name

    @property
    def remote_object_name(self) -> str:
        return self._remote_object_name

    @property
    def script(self) -> Optional[str]:
        return self._script

    @property
    def tags(self) -> Optional[List[str]]:
        return self._tags

    @property
    def group(self) -> Optional[str]:
        return self._group

    @property
    def metadata(self) -> AudioMeta:
        return self._metadata

    @property
    def type(self) -> QuestionFileType:
        return self._type

    @property
    def order_in_group(self) -> int:
        return self._order_in_group

    def set_upload_at(self, start_at: str, finish_at: str) -> None:
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
            "tag": self._tags,
            "type": self._type,
            "script": self._script,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }

    def to_create_file_dict(self) -> Dict[str, Any]:
        return {
            "original_uri": self._path,
            "processed_uri": self._remote_object_name,
            "duration": self._metadata.duration_in_ms,
            "tags": self._tags,
            "type": self._type,
            "script": self._script,
            "group": self._group,
            "order_in_group": self._order_in_group,
        }
