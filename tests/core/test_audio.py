import os
import shutil
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import soundfile as sf

from podonos.common.enum import QuestionFileType
from podonos.core.file import Audio, AudioGroup, AudioMeta, File
from podonos.errors import InvalidFileError

TESTDATA_SPEECH_TWO_CH1_M4A = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.m4a"
)
TESTDATA_SPEECH_TWO_CH1_FLAC = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.flac"
)
TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
TESTDATA_SPEECH_TWO_CH1_WAV = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.wav"
)
TESTDATA_SPEECH_TWO_CH2_WAV = os.path.join(
    os.path.dirname(__file__), "speech_two_ch2.wav"
)


class TestAudioMeta(unittest.TestCase):
    def setUp(self):
        """Set up test file paths"""
        self.test_dir = os.path.dirname(__file__)
        self.test_files = {
            "mp3": os.path.join(self.test_dir, "speech_ch1.mp3"),
            "wav_mono": os.path.join(self.test_dir, "speech_two_ch1.wav"),
            "wav_stereo": os.path.join(self.test_dir, "speech_two_ch2.wav"),
            "flac": os.path.join(self.test_dir, "speech_two_ch1.flac"),
            "m4a": os.path.join(self.test_dir, "speech_two_ch1.m4a"),
        }

    def test_should_read_mono_mp3_metadata_correctly(self):
        # Given
        mp3_path = self.test_files["mp3"]
        expected_channels = 1
        expected_framerate = 24000
        expected_duration = 2935

        # When
        meta = AudioMeta(mp3_path)

        # Then
        self.assertEqual(meta.nchannels, expected_channels)
        self.assertEqual(meta.framerate, expected_framerate)
        self.assertEqual(meta.duration_in_ms, expected_duration)

    def test_audio_meta_ch1_wav(self):
        meta = AudioMeta(TESTDATA_SPEECH_TWO_CH1_WAV)
        self.assertTrue(meta.nchannels == 1)
        self.assertTrue(meta.framerate == 16000)
        self.assertTrue(meta.duration_in_ms == 558)

    def test_audio_meta_ch2_wav(self):
        meta = AudioMeta(TESTDATA_SPEECH_TWO_CH2_WAV)
        self.assertTrue(meta.nchannels == 2)
        self.assertTrue(meta.framerate == 16000)
        self.assertTrue(meta.duration_in_ms == 558)

    def test_audio_meta_ch1_flac(self):
        meta = AudioMeta(TESTDATA_SPEECH_TWO_CH1_FLAC)
        self.assertTrue(meta.nchannels == 1)
        self.assertTrue(meta.framerate == 16000)
        self.assertTrue(meta.duration_in_ms == 558)

    def test_audio_meta_unsupported_format(self):
        """Test that unsupported formats raise InvalidFileError."""
        with self.assertRaises(InvalidFileError) as context:
            AudioMeta(TESTDATA_SPEECH_TWO_CH1_M4A)
        self.assertIn("Unsupported", str(context.exception))


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")
        self.test_file = File(
            path=self.test_wav,
            model_tag="test_model",
            tags=["test", "mono"],
            script="test script",
            is_ref=False,
        )

    def test_should_create_audio_from_file_correctly(self):
        # Given
        group = "test_group"
        type = QuestionFileType.STIMULUS
        order = 1
        remote_path = "remote/path/audio.wav"

        # When
        audio = Audio(
            path=self.test_wav,
            name="speech_two_ch1.wav",
            remote_object_name=remote_path,
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group=group,
            type=type,
            order_in_group=order,
        )

        # Then
        self.assertEqual(audio.path, self.test_wav)
        self.assertEqual(audio.group, group)
        self.assertEqual(audio.type, type)
        self.assertEqual(audio.order_in_group, order)
        self.assertEqual(audio.remote_object_name, remote_path)
        self.assertEqual(audio.model_tag, "test_model")
        self.assertEqual(audio.tags, ["test", "mono"])
        self.assertEqual(audio.script, "test script")
        self.assertFalse(audio.is_ref)

    def test_should_validate_audio_metadata(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        meta = audio._metadata  # type: ignore[attr-defined]

        # Then
        self.assertEqual(meta.nchannels, 1)
        self.assertEqual(meta.framerate, 16000)
        self.assertEqual(meta.duration_in_ms, 558)

    def test_should_track_upload_timestamps(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        now = datetime.now()
        audio.set_upload_at(now.isoformat(), now.isoformat())

        # Then
        assert audio._upload_start_at is not None  # type: ignore[attr-defined]
        assert audio._upload_finish_at is not None  # type: ignore[attr-defined]

    def test_should_set_integrity_info(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # Then
        self.assertEqual(audio.content_md5, "AA259hLYqLX6hjV81ve5Cg==")
        self.assertEqual(audio.file_size, 17920)

    def test_should_include_integrity_info_in_create_file_dict(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # When
        file_dict = audio.to_create_file_dict()

        # Then
        self.assertEqual(file_dict["content_md5"], "AA259hLYqLX6hjV81ve5Cg==")
        self.assertEqual(file_dict["file_size"], 17920)

    def test_should_have_none_integrity_info_before_set(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # Then
        self.assertIsNone(audio.content_md5)
        self.assertIsNone(audio.file_size)

    def test_should_create_file_dict_correctly(self):
        # Given
        audio = Audio(
            path=self.test_wav,
            name="speech_two_ch1.wav",
            remote_object_name="remote/path.wav",
            script="test script",
            tags=["test", "mono"],
            model_tag="test_model",
            is_ref=False,
            group="test_group",
            type=QuestionFileType.STIMULUS,
            order_in_group=1,
        )

        # When
        file_dict = audio.to_create_file_dict()

        # Then
        self.assertEqual(file_dict["original_name"], self.test_wav)
        self.assertEqual(file_dict["uploaded_file_name"], "remote/path.wav")
        self.assertEqual(file_dict["duration"], 558)
        self.assertEqual(file_dict["model_tag"], "test_model")
        self.assertEqual(file_dict["tags"], ["test", "mono"])
        self.assertEqual(file_dict["script"], "test script")
        self.assertEqual(file_dict["group"], "test_group")
        self.assertEqual(file_dict["type"], QuestionFileType.STIMULUS.value)
        self.assertEqual(file_dict["order_in_group"], 1)


class TestAudioGroup(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_should_create_audio_group_correctly(self):
        # Given
        group_id = "test_group"
        audio1 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote1.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        audio2 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote2.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.REF,
            order_in_group=1,
        )
        created_at = datetime.now()

        # When
        group = AudioGroup(
            group_id=group_id, audios=[audio1, audio2], created_at=created_at
        )

        # Then
        self.assertEqual(group.group_id, group_id)
        self.assertEqual(len(group.audios), 2)
        self.assertEqual(group.created_at, created_at)
        self.assertEqual(group.audios[0].order_in_group, 0)
        self.assertEqual(group.audios[1].order_in_group, 1)

    def test_should_maintain_audio_order(self):
        # Given
        group_id = "test_group"
        audio1 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote1.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        audio2 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote2.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.REF,
            order_in_group=1,
        )

        # When
        group = AudioGroup(
            group_id=group_id, audios=[audio1, audio2], created_at=datetime.now()
        )

        # Then
        self.assertEqual(group.audios[0].order_in_group, 0)
        self.assertEqual(group.audios[1].order_in_group, 1)

    def test_should_convert_to_dict_correctly(self):
        # Given
        group_id = "test_group"
        audio = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        group = AudioGroup(group_id=group_id, audios=[audio], created_at=datetime.now())

        # When
        group_dict = group.to_dict()

        # Then
        self.assertEqual(group_dict["group_id"], group_id)
        self.assertEqual(len(group_dict["audios"]), 1)
        self.assertEqual(group_dict["audios"][0]["remote_name"], "remote.wav")
        self.assertEqual(
            group_dict["audios"][0]["type"], QuestionFileType.STIMULUS.value
        )

    def test_should_raise_error_for_mismatched_group_ids(self):
        # Given
        group_id = "test_group"
        audio1 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group=group_id,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        audio2 = Audio(
            path=self.test_wav,
            name=os.path.basename(self.test_wav),
            remote_object_name="remote.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group="different_group",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        created_at = datetime.now()

        # When/Then
        with self.assertRaises(ValueError):
            AudioGroup(
                group_id=group_id, audios=[audio1, audio2], created_at=created_at
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
        # Write garbage data that looks nothing like a valid audio file
        # This will cause soundfile to fail when trying to open it
        with open(path, "wb") as f:
            f.write(b"NOT_A_VALID_AUDIO_FILE_HEADER")
            f.write(os.urandom(200))
        return path

    @classmethod
    def _create_truncated_wav(cls):
        """Create a WAV file with header truncated mid-way."""
        path = os.path.join(cls.fixtures_dir, "truncated.wav")
        # Write only partial WAV header - this will fail to parse
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
        with patch("podonos.core.file.log") as mock_log:
            with patch("podonos.core.file.sf.SoundFile") as mock_sf:
                mock_file = MagicMock()
                mock_file.frames = 44100 * 60 * 15  # 15 minutes at 44.1kHz
                mock_file.channels = 1
                mock_file.samplerate = 44100
                mock_file.read.return_value = np.zeros(1024)
                mock_file.__enter__ = MagicMock(return_value=mock_file)
                mock_file.__exit__ = MagicMock(return_value=False)
                mock_sf.return_value = mock_file

                from podonos.core.file import AudioMeta

                meta = AudioMeta.__new__(AudioMeta)
                meta.filepath = "test.wav"

                nchannels, framerate, duration = meta._validate_and_extract_audio_info(
                    "test.wav"
                )

                warning_calls = [str(call) for call in mock_log.warning.call_args_list]
                self.assertTrue(
                    any("long" in call.lower() for call in warning_calls),
                    f"Expected warning about long audio, got: {warning_calls}",
                )
                self.assertGreater(duration, 600000)

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
