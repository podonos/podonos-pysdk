import wave
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

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
        """ Gets info from an audio file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
        """

        # Check if this is wav or mp3.
        suffix = Path(path).suffix
        assert suffix == '.wav' or suffix == '.mp3', \
            f"Unsupported file format: {path}. It must be either wav or mp3."
        if suffix == '.wav':
            return self._get_wave_info(path)
        elif suffix == '.mp3':
            return self._get_mp3_info(path)
        return 0, 0, 0

    def _get_wave_info(self, filepath: str) -> Tuple[int, int, int]:
        """ Gets info from a wave file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
            wave.Error: if the file doesn't read properly.
        """
        wav = wave.open(filepath, "r")
        nchannels, sampwidth, framerate, nframes, comptype, compname = wav.getparams()
        assert comptype == 'NONE'
        duration_in_ms = int(nframes * 1000.0 / float(framerate))
        return nchannels, framerate, duration_in_ms


    def _get_mp3_info(self, filepath: str) -> Tuple[int, int, int]:
        """ Gets info from a mp3 file.

        Returns:
            nchannels: Number of channels
            framerate: Number of frames per second. Same as the sampling rate.
            duration_in_ms: Total length of the audio in milliseconds

        Raises:
            FileNotFoundError: if the file is not found.
        """
        # TODO parse the mp3 without pydub, which installs ffmpeg and causes lots of error.
        return 0, 0, 0

class Audio:
    _path: str
    _name: str
    _remote_name: str
    _metadata: AudioMeta
    _upload_start_at: Optional[str] = None
    _upload_finish_at: Optional[str] = None
    _tag: Optional[str] = None
    _group: Optional[str] = None
    
    def __init__(
        self, 
        path: str,
        name: str, 
        remote_name: str,
        tag: Optional[str],
        group: Optional[str]
    ) -> None:
        self._path = path
        self._name = name
        self._remote_name = remote_name
        self._metadata = AudioMeta(path)
        self._tag = tag
        self._group = group

    @property
    def path(self) -> str:
        return self._path

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def remote_name(self) -> str:
        return self._remote_name
    
    @property
    def tag(self) -> Optional[str]:
        return self._tag
    
    @property
    def group(self) -> Optional[str]:
        return self._group

    def set_upload_at(self, start_at: str, finish_at: str) -> None:
        self._upload_start_at = start_at
        self._upload_finish_at = finish_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self._name,
            "remote_name": self._remote_name, 
            "nchannels": self._metadata.nchannels,
            "framerate": self._metadata.framerate,
            "duration_in_ms": self._metadata.duration_in_ms,
            "upload_start_at": self._upload_start_at,
            "upload_finish_at": self._upload_finish_at,
            "tag": self._tag,
            "group": self._group
        }