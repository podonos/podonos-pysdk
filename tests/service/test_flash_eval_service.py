import os
import unittest
from unittest.mock import Mock, mock_open, patch

from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.entity.flash_eval import FlashEvalResult
from podonos.service.flash_eval_service import FlashEvalService


class TestFlashEvalService(unittest.TestCase):
    def setUp(self):
        self.mock_api_client = Mock(spec=APIClient)
        self.service = FlashEvalService(self.mock_api_client)

    def _setup_init_response(self, key="test-key-123", url="https://storage.example.com/presigned"):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": key, "urls": [url]}
        mock_response.raise_for_status.return_value = None
        return mock_response

    def _setup_upload_response(self):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        return mock_response

    def _setup_eval_response(self, naturalness=3.6):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "scores": {"naturalness": naturalness},
            "files": [
                {"filename": "test.wav", "filetype": "TARGET_1", "mimetype": "audio/wav"}
            ],
            "message": "success",
        }
        mock_response.raise_for_status.return_value = None
        return mock_response

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake audio data"))
    def test_eval_full_flow(self, mock_access, mock_isfile):
        """Test the complete 3-step eval flow."""
        init_response = self._setup_init_response()
        upload_response = self._setup_upload_response()
        eval_response = self._setup_eval_response(naturalness=4.1)

        self.mock_api_client.post.side_effect = [init_response, eval_response]
        self.mock_api_client.external_put.return_value = upload_response

        result = self.service.eval("/path/to/test.wav")

        self.assertIsInstance(result, FlashEvalResult)
        self.assertEqual(result.naturalness, 4.1)

        # Verify init call
        init_call = self.mock_api_client.post.call_args_list[0]
        self.assertEqual(init_call[0][0], "flash/v1/init")
        init_payload = init_call[1]["data"] if "data" in init_call[1] else init_call[0][1]
        self.assertEqual(init_payload["files"][0]["filename"], "test.wav")
        self.assertEqual(init_payload["files"][0]["filetype"], "TARGET_1")
        self.assertEqual(init_payload["files"][0]["mimetype"], "audio/wav")

        # Verify upload call sends bytes (not file handle) for retry safety
        upload_call = self.mock_api_client.external_put.call_args
        self.assertEqual(upload_call[0][0], "https://storage.example.com/presigned")
        upload_headers = upload_call[1]["headers"]
        self.assertEqual(upload_headers["Content-Type"], "audio/wav")
        self.assertEqual(upload_headers["x-goog-resumable"], "false")
        self.assertIsInstance(upload_call[1]["data"], bytes)

        # Verify eval call
        eval_call = self.mock_api_client.post.call_args_list[1]
        self.assertEqual(eval_call[0][0], "flash/v1/eval")
        eval_payload = eval_call[1]["data"] if "data" in eval_call[1] else eval_call[0][1]
        self.assertEqual(eval_payload["key"], "test-key-123")
        self.assertIn("request_time", eval_payload)

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_init_failure_raises_http_error(self, mock_access, mock_isfile):
        """Test that init failure raises HTTPError."""
        error_response = Mock()
        error_response.raise_for_status.side_effect = Exception("Server error")
        self.mock_api_client.post.return_value = error_response

        with self.assertRaises(HTTPError):
            self.service._init(filename="test.wav", mimetype="audio/wav")

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_init_empty_urls_raises_http_error(self, mock_access, mock_isfile):
        """Test that empty urls in init response raises HTTPError."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "k", "urls": []}
        mock_response.raise_for_status.return_value = None
        self.mock_api_client.post.return_value = mock_response

        with self.assertRaises(HTTPError) as context:
            self.service._init(filename="test.wav", mimetype="audio/wav")
        self.assertIn("no upload URLs", str(context.exception))

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_init_missing_key_raises_http_error(self, mock_access, mock_isfile):
        """Test that missing key in init response raises HTTPError."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"urls": ["https://example.com"]}
        mock_response.raise_for_status.return_value = None
        self.mock_api_client.post.return_value = mock_response

        with self.assertRaises(HTTPError) as context:
            self.service._init(filename="test.wav", mimetype="audio/wav")
        self.assertIn("missing 'key'", str(context.exception))

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake audio data"))
    def test_upload_failure_raises_http_error(self, mock_access, mock_isfile):
        """Test that upload failure raises HTTPError."""
        error_response = Mock()
        error_response.raise_for_status.side_effect = Exception("Upload failed")
        self.mock_api_client.external_put.return_value = error_response

        with self.assertRaises(HTTPError):
            self.service._upload(
                presigned_url="https://storage.example.com/presigned",
                file_path="/path/to/test.wav",
                mimetype="audio/wav",
            )

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_eval_step_failure_raises_http_error(self, mock_access, mock_isfile):
        """Test that eval step failure raises HTTPError."""
        error_response = Mock()
        error_response.raise_for_status.side_effect = Exception("Eval failed")
        self.mock_api_client.post.return_value = error_response

        with self.assertRaises(HTTPError):
            self.service._eval(key="test-key")

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_init_returns_key_and_url(self, mock_access, mock_isfile):
        """Test that _init returns the correct key and presigned URL."""
        init_response = self._setup_init_response(key="my-key", url="https://example.com/upload")
        self.mock_api_client.post.return_value = init_response

        key, url = self.service._init(filename="audio.mp3", mimetype="audio/mpeg")

        self.assertEqual(key, "my-key")
        self.assertEqual(url, "https://example.com/upload")

    @patch("os.path.isfile", return_value=True)
    @patch("os.access", return_value=True)
    def test_eval_step_returns_result(self, mock_access, mock_isfile):
        """Test that _eval returns FlashEvalResult."""
        eval_response = self._setup_eval_response(naturalness=2.5)
        self.mock_api_client.post.return_value = eval_response

        result = self.service._eval(key="test-key")

        self.assertIsInstance(result, FlashEvalResult)
        self.assertEqual(result.naturalness, 2.5)
        self.assertEqual(result.message, "success")


if __name__ == "__main__":
    unittest.main()
