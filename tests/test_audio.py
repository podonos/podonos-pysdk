import os
import podonos
import unittest
from unittest import mock
from podonos.core.audio import AudioMeta

TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), 'speech_ch1.mp3')
TESTDATA_SPEECH_TWO_CH1_WAV = os.path.join(os.path.dirname(__file__), 'speech_two_ch1.wav')
TESTDATA_SPEECH_TWO_CH2_WAV = os.path.join(os.path.dirname(__file__), 'speech_two_ch2.wav')


class TestAudioMeta(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
