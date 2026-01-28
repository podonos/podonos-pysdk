"""Tests for audio file validation that require numpy and soundfile."""

import os
import shutil
import unittest
from unittest.mock import patch

import pytest

from podonos.core.file import AudioMeta
from podonos.errors import InvalidFileError

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")


TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
TESTDATA_SPEECH_TWO_CH1_WAV = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.wav"
)
TESTDATA_SPEECH_TWO_CH1_FLAC = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.flac"
)


class TestAudioValidation(unittest.TestCase):
    """Tests for audio file validation before upload."""

    @classmethod
    def setUpClass(cls):
        """Create test fixture files."""
        cls.fixtures_dir = os.path.join(os.path.dirname(__file__), "test_fixtures")
        os.makedirs(cls.fixtures_dir, exist_ok=True)
        cls._create_corrupted_wav()
        cls._create_truncated_wav()
        cls._create_empty_wav()
        cls._create_format_mismatch()
        cls._create_short_audio()

    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures."""
        shutil.rmtree(cls.fixtures_dir, ignore_errors=True)

    @classmethod
    def _create_corrupted_wav(cls):
        """Create a file with WAV extension but completely invalid content."""
        path = os.path.join(cls.fixtures_dir, "corrupted.wav")
        with open(path, "wb") as f:
            f.write(b"NOT_A_VALID_AUDIO_FILE_HEADER")
            f.write(os.urandom(200))
        return path

    @classmethod
    def _create_truncated_wav(cls):
        """Create a WAV file with header truncated mid-way."""
        path = os.path.join(cls.fixtures_dir, "truncated.wav")
        with open(path, "wb") as f:
            f.write(b"RIFF")
            f.write((1000).to_bytes(4, "little"))
            f.write(b"WAV")  # Truncated - should be "WAVE"
        return path

    @classmethod
    def _create_empty_wav(cls):
        """Create a WAV file with zero frames."""
        path = os.path.join(cls.fixtures_dir, "empty.wav")
        sf.write(path, np.array([], dtype=np.float32), 44100)
        return path

    @classmethod
    def _create_format_mismatch(cls):
        """Create an MP3 file with .wav extension."""
        src_path = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
        dst_path = os.path.join(cls.fixtures_dir, "fake_mp3.wav")
        shutil.copy(src_path, dst_path)
        return dst_path

    @classmethod
    def _create_short_audio(cls):
        """Create a very short audio file (<500ms) for warning test."""
        path = os.path.join(cls.fixtures_dir, "short_audio.wav")
        audio_data = np.random.randn(11025).astype(np.float32)  # ~250ms at 44100Hz
        sf.write(path, audio_data, 44100)
        return path

    def test_should_raise_for_corrupted_audio(self):
        """Test that corrupted audio files raise InvalidFileError."""
        with self.assertRaises(InvalidFileError) as ctx:
            AudioMeta(os.path.join(self.fixtures_dir, "corrupted.wav"))
        self.assertTrue(
            "corrupted" in str(ctx.exception).lower()
            or "cannot read" in str(ctx.exception).lower()
        )

    def test_should_raise_for_truncated_audio(self):
        """Test that truncated audio files raise InvalidFileError."""
        with self.assertRaises(InvalidFileError) as ctx:
            AudioMeta(os.path.join(self.fixtures_dir, "truncated.wav"))
        self.assertTrue(
            "truncated" in str(ctx.exception).lower()
            or "corrupted" in str(ctx.exception).lower()
        )

    def test_should_raise_for_empty_audio(self):
        """Test that empty audio files raise InvalidFileError."""
        with self.assertRaises(InvalidFileError) as ctx:
            AudioMeta(os.path.join(self.fixtures_dir, "empty.wav"))
        self.assertIn("no audio data", str(ctx.exception).lower())

    def test_should_raise_for_format_mismatch(self):
        """Test that format mismatch raises InvalidFileError."""
        with self.assertRaises(InvalidFileError) as ctx:
            AudioMeta(os.path.join(self.fixtures_dir, "fake_mp3.wav"))
        self.assertIn("does not match", str(ctx.exception))

    def test_should_warn_for_very_short_audio(self):
        """Test that very short audio files trigger a warning."""
        with patch("podonos.core.file.log") as mock_log:
            meta = AudioMeta(os.path.join(self.fixtures_dir, "short_audio.wav"))
            warning_calls = [call for call in mock_log.warning.call_args_list]
            self.assertTrue(
                any("short" in str(call).lower() for call in warning_calls),
                f"Expected warning about short audio, got: {warning_calls}",
            )
            self.assertGreater(meta.duration_in_ms, 0)
            self.assertLess(meta.duration_in_ms, 500)

    def test_should_warn_for_low_sample_rate(self):
        """Test that low sample rate audio files trigger a warning."""
        low_sr_path = os.path.join(self.fixtures_dir, "low_samplerate.wav")
        audio_data = np.random.randn(4000).astype(np.float32)
        sf.write(low_sr_path, audio_data, 4000)

        with patch("podonos.core.file.log") as mock_log:
            meta = AudioMeta(low_sr_path)
            warning_calls = [call for call in mock_log.warning.call_args_list]
            self.assertTrue(
                any("sample rate" in str(call).lower() for call in warning_calls),
                f"Expected warning about low sample rate, got: {warning_calls}",
            )
            self.assertEqual(meta.framerate, 4000)

    def test_should_warn_for_very_long_audio(self):
        """Test that very long audio files (>10 min) trigger a warning."""
        # Create a long audio file (11 minutes at 8000Hz to keep file size small)
        long_audio_path = os.path.join(self.fixtures_dir, "long_audio.wav")
        # 8000 Hz * 60 sec * 11 min = 5,280,000 samples (~11 minutes)
        duration_samples = 8000 * 60 * 11
        audio_data = np.zeros(duration_samples, dtype=np.float32)
        sf.write(long_audio_path, audio_data, 8000)

        with patch("podonos.core.file.log") as mock_log:
            meta = AudioMeta(long_audio_path)
            warning_calls = [str(call) for call in mock_log.warning.call_args_list]
            self.assertTrue(
                any("long" in call.lower() for call in warning_calls),
                f"Expected warning about long audio, got: {warning_calls}",
            )
            self.assertGreater(meta.duration_in_ms, 600000)  # > 10 minutes

    def test_valid_wav_passes_validation(self):
        """Test that valid WAV files pass validation."""
        meta = AudioMeta(TESTDATA_SPEECH_TWO_CH1_WAV)
        self.assertGreater(meta.duration_in_ms, 0)
        self.assertGreater(meta.nchannels, 0)
        self.assertGreater(meta.framerate, 0)

    def test_valid_mp3_passes_validation(self):
        """Test that valid MP3 files pass validation."""
        meta = AudioMeta(TESTDATA_SPEECH_CH1_MP3)
        self.assertGreater(meta.duration_in_ms, 0)
        self.assertGreater(meta.nchannels, 0)
        self.assertGreater(meta.framerate, 0)

    def test_valid_flac_passes_validation(self):
        """Test that valid FLAC files pass validation."""
        meta = AudioMeta(TESTDATA_SPEECH_TWO_CH1_FLAC)
        self.assertGreater(meta.duration_in_ms, 0)
        self.assertGreater(meta.nchannels, 0)
        self.assertGreater(meta.framerate, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
