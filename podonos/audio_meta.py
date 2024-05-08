"""
Extract metadata from audio files
"""
import wave
from dataclasses import dataclass

from pathlib import Path
from typing import Tuple, Union
from mutagen.mp3 import MP3

@dataclass
class AudioInfo:
    """ Audio information class.

    Attributes:
        nchannels: Number of channels
        framerate: Number of frames per second. Same as the sampling rate.
        duration_in_ms: Total length of the audio in milliseconds
    """
    nchannels: int
    framerate: int
    duration_in_ms: int
    
    def to_values(self) -> Tuple[int, int, int]:
        return self.nchannels, self.framerate, self.duration_in_ms

def get_audio_info(path: str) -> Union[Tuple[int, int, int], None]:
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
        return get_wave_info(path).to_values()
    elif suffix == '.mp3':
        return get_mp3_info(path).to_values()


def get_wave_info(filepath: str) -> AudioInfo:
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
    return AudioInfo(nchannels, framerate, duration_in_ms)


def get_mp3_info(filepath: str) -> AudioInfo:
    """ Gets info from a mp3 file.

    Returns:
        nchannels: Number of channels
        framerate: Number of frames per second. Same as the sampling rate.
        duration_in_ms: Total length of the audio in milliseconds

    Raises:
        FileNotFoundError: if the file is not found.
    """
    # TODO parse the mp3 without pydub, which installs ffmpeg and causes lots of error.
    try:
        audio = MP3(filepath)
        return AudioInfo(
            nchannels=audio.info.channels, # type: ignore
            framerate=audio.info.sample_rate, # type: ignore
            duration_in_ms=int(audio.info.length * 1000)
        )
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filepath}")