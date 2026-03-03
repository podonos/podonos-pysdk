import unittest
from unittest.mock import patch

from podonos.core.file import File
from podonos.entity.flash_eval import FlashEvalResult


class TestFlashEvalResult(unittest.TestCase):
    def _create_file(self, path="/path/to/audio.wav"):
        """Helper to create a File. Caller must patch os.path.isfile and os.access."""
        return File(path=path, model_tag="flash_eval")

    @patch("os.access", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_from_dict_with_scores(self, mock_isfile, mock_access):
        file = self._create_file()
        data = {
            "scores": {"naturalness": 3.6},
            "message": "success",
        }
        result = FlashEvalResult.from_dict(data, file=file, eval_id="eval-123")
        self.assertEqual(result.naturalness, 3.6)
        self.assertEqual(result.file.path, "/path/to/audio.wav")
        self.assertEqual(result.eval_id, "eval-123")
        self.assertEqual(result.message, "success")

    @patch("os.access", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_from_dict_without_scores(self, mock_isfile, mock_access):
        file = self._create_file()
        data = {"message": None}
        result = FlashEvalResult.from_dict(data, file=file)
        self.assertIsNone(result.naturalness)
        self.assertIsNone(result.eval_id)
        self.assertIsNone(result.message)

    @patch("os.access", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_from_dict_empty(self, mock_isfile, mock_access):
        file = self._create_file()
        result = FlashEvalResult.from_dict({}, file=file)
        self.assertIsNone(result.naturalness)
        self.assertIsNone(result.message)

    @patch("os.access", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_from_dict_scores_not_dict(self, mock_isfile, mock_access):
        file = self._create_file()
        data = {"scores": "invalid"}
        result = FlashEvalResult.from_dict(data, file=file)
        self.assertIsNone(result.naturalness)

    @patch("os.access", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_file_preserves_original_path(self, mock_isfile, mock_access):
        file = self._create_file(path="/home/user/recordings/speech.wav")
        data = {"scores": {"naturalness": 4.2}}
        result = FlashEvalResult.from_dict(data, file=file)
        self.assertEqual(result.file.path, "/home/user/recordings/speech.wav")
        self.assertEqual(result.file.model_tag, "flash_eval")


if __name__ == "__main__":
    unittest.main()
