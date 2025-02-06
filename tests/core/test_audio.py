import os
import unittest
from datetime import datetime
from unittest.mock import patch

from podonos.core.audio import AudioMeta, Audio, AudioGroup
from podonos.core.file import File
from podonos.common.enum import QuestionFileType

TESTDATA_SPEECH_TWO_CH1_M4A = os.path.join(os.path.dirname(__file__), "speech_two_ch1.m4a")
TESTDATA_SPEECH_TWO_CH1_FLAC = os.path.join(os.path.dirname(__file__), "speech_two_ch1.flac")
TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
TESTDATA_SPEECH_TWO_CH1_WAV = os.path.join(os.path.dirname(__file__), "speech_two_ch1.wav")
TESTDATA_SPEECH_TWO_CH2_WAV = os.path.join(os.path.dirname(__file__), "speech_two_ch2.wav")


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
        with self.assertRaises(AssertionError) as context:
            AudioMeta(TESTDATA_SPEECH_TWO_CH1_M4A)
        self.assertTrue("Unsupported file format" in str(context.exception))


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")
        self.test_file = File(path=self.test_wav, model_tag="test_model", tags=["test", "mono"], script="test script", is_ref=False)

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
        meta = audio._metadata

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
        self.assertIsNotNone(audio._upload_start_at)
        self.assertIsNotNone(audio._upload_finish_at)

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
        self.assertEqual(file_dict["processed_uri"], "remote/path.wav")
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
        group = AudioGroup(group_id=group_id, audios=[audio1, audio2], created_at=created_at)

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
        group = AudioGroup(group_id=group_id, audios=[audio1, audio2], created_at=datetime.now())

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
        self.assertEqual(group_dict["audios"][0]["type"], QuestionFileType.STIMULUS.value)

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
            AudioGroup(group_id=group_id, audios=[audio1, audio2], created_at=created_at)


if __name__ == "__main__":
    unittest.main(verbosity=2)
