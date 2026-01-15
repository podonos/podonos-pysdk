import os
import tempfile
import unittest

from podonos.common.util import calculate_file_md5_base64


class TestCalculateFileMd5Base64(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "core")
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_should_calculate_md5_and_size_for_wav_file(self):
        # When
        md5_hash, file_size = calculate_file_md5_base64(self.test_wav)

        # Then
        self.assertEqual(len(md5_hash), 24)
        self.assertGreater(file_size, 0)
        self.assertEqual(file_size, os.path.getsize(self.test_wav))

    def test_should_return_consistent_md5_for_same_file(self):
        # When
        md5_hash1, size1 = calculate_file_md5_base64(self.test_wav)
        md5_hash2, size2 = calculate_file_md5_base64(self.test_wav)

        # Then
        self.assertEqual(md5_hash1, md5_hash2)
        self.assertEqual(size1, size2)

    def test_should_return_different_md5_for_different_files(self):
        # Given
        test_wav2 = os.path.join(self.test_dir, "speech_two_ch2.wav")

        # When
        md5_hash1, _ = calculate_file_md5_base64(self.test_wav)
        md5_hash2, _ = calculate_file_md5_base64(test_wav2)

        # Then
        self.assertNotEqual(md5_hash1, md5_hash2)

    def test_should_raise_error_for_nonexistent_file(self):
        # When/Then
        with self.assertRaises(FileNotFoundError):
            calculate_file_md5_base64("/nonexistent/path/file.wav")

    def test_should_handle_empty_file(self):
        # Given
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            # When
            md5_hash, file_size = calculate_file_md5_base64(temp_path)

            # Then
            self.assertEqual(len(md5_hash), 24)
            self.assertEqual(file_size, 0)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    unittest.main()
