"""
Extract metadata from audio files
"""

import wave


def get_wave_info(filepath):
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


def get_mp3_info(filepath):
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
