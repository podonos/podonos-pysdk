import io
import math
import unittest
from unittest.mock import Mock, patch

import requests
from requests import Response

from podonos.core.api import APIClient


class TestAPIClientRetryLogging(unittest.TestCase):
    def setUp(self):
        self.client = APIClient(
            "test_api_key",
            "https://api.example.com",
            max_retries=1,
            retry_delay=0,
            backoff_factor=1,
        )

    @patch("time.sleep")
    @patch("podonos.core.api.log.warning")
    @patch("requests.post")
    def test_retry_log_includes_safe_context(self, mock_post: Mock, mock_warning: Mock, mock_sleep: Mock):
        response = Response()
        response.status_code = 200
        response._content = b"{}"
        mock_post.side_effect = [
            requests.exceptions.ReadTimeout("read timeout"),
            response,
        ]

        self.client.post(
            "evaluations/eval-id/files/verify",
            data={"files": []},
            timeout=(5, 120),
            context={
                "evaluation_id": "eval-id",
                "batch_index": 3,
                "batch_size": 100,
                "file_count": 100,
            },
        )

        log_message = mock_warning.call_args.args[0]
        self.assertIn("method=POST", log_message)
        self.assertIn("endpoint=evaluations/eval-id/files/verify", log_message)
        self.assertIn("timeout=(5, 120)", log_message)
        self.assertIn("batch_index=3", log_message)
        self.assertIn("batch_size=100", log_message)
        self.assertIn("file_count=100", log_message)

    @patch("time.sleep")
    @patch("podonos.core.api.log.warning")
    @patch("requests.put")
    def test_external_put_retry_log_redacts_presigned_url_and_secrets(
        self, mock_put: Mock, mock_warning: Mock, mock_sleep: Mock
    ):
        response = Response()
        response.status_code = 200
        response._content = b""
        raw_url = (
            "https://bucket.s3.amazonaws.com/file.wav"
            "?X-Amz-Signature=SECRET&X-Amz-Credential=CREDENTIAL"
        )
        mock_put.side_effect = [
            requests.exceptions.ReadTimeout(f"read timeout for {raw_url} X-API-KEY=SECRET"),
            response,
        ]

        self.client.external_put(
            raw_url,
            data=b"audio",
            timeout=(10, 300),
            context={"evaluation_id": "eval-id"},
        )

        log_message = mock_warning.call_args.args[0]
        self.assertIn("external_endpoint=presigned_put", log_message)
        self.assertIn("timeout=(10, 300)", log_message)
        self.assertIn("evaluation_id=eval-id", log_message)
        self.assertNotIn("X-Amz-Signature=SECRET", log_message)
        self.assertNotIn("X-Amz-Credential=CREDENTIAL", log_message)
        self.assertNotIn("X-API-KEY=SECRET", log_message)
        self.assertNotIn(raw_url, log_message)

    @patch("time.sleep")
    @patch("requests.put")
    def test_external_put_rewinds_file_like_data_between_retries(
        self, mock_put: Mock, mock_sleep: Mock
    ):
        bodies = []

        def put_side_effect(*args, **kwargs):
            bodies.append(kwargs["data"].read())
            response = Response()
            response.status_code = 500 if len(bodies) == 1 else 200
            response._content = b""
            return response

        mock_put.side_effect = put_side_effect
        payload = io.BytesIO(b"full audio payload")

        response = self.client.external_put(
            "https://bucket.s3.amazonaws.com/file.wav",
            data=payload,
            timeout=(10, 300),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(bodies, [b"full audio payload", b"full audio payload"])

    def test_rejects_invalid_public_timeout_values(self):
        invalid_timeouts = [
            5,
            (0, 30),
            (5, -1),
            ("5", 30),
            (True, 30),
            (5,),
            (math.nan, 30),
            (5, math.inf),
        ]

        for timeout in invalid_timeouts:
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.client.get("version/sdk", timeout=timeout)  # type: ignore[arg-type]

        with self.assertRaises(ValueError):
            self.client.external_put(
                "https://bucket.s3.amazonaws.com/file.wav",
                data=b"audio",
                timeout=(10, 0),
            )

    def test_sanitize_log_message_redacts_authorization_bearer_value(self):
        message = self.client._sanitize_log_message(  # type: ignore[attr-defined]
            "Authorization: Bearer SECRET_TOKEN"
        )

        self.assertNotIn("SECRET_TOKEN", message)
        self.assertIn("[REDACTED]", message)

    @patch("time.sleep")
    @patch("podonos.core.api.log.warning")
    @patch("requests.get")
    def test_retry_context_values_are_redacted(
        self, mock_get: Mock, mock_warning: Mock, mock_sleep: Mock
    ):
        response = Response()
        response.status_code = 200
        response._content = b"{}"
        mock_get.side_effect = [
            requests.exceptions.ReadTimeout("temporary timeout"),
            response,
        ]

        self.client.get(
            "evaluations/eval-id",
            context={
                "evaluation_id": "eval-id X-API-KEY=SECRET",
                "file_count": "Authorization: Bearer TOKEN",
            },
        )

        log_message = mock_warning.call_args.args[0]
        self.assertNotIn("SECRET", log_message)
        self.assertNotIn("TOKEN", log_message)
        self.assertIn("[REDACTED]", log_message)

    @patch("time.sleep")
    @patch("podonos.core.api.log.warning")
    @patch("requests.post")
    def test_caller_context_cannot_override_reserved_retry_keys(
        self, mock_post: Mock, mock_warning: Mock, mock_sleep: Mock
    ):
        response = Response()
        response.status_code = 200
        response._content = b"{}"
        mock_post.side_effect = [
            requests.exceptions.ReadTimeout("temporary timeout"),
            response,
        ]

        self.client.post(
            "evaluations/safe-endpoint",
            data={},
            timeout=(5, 30),
            context={
                "method": "LEAKY",
                "endpoint": (
                    "https://bucket.s3.amazonaws.com/file.wav"
                    "?X-Amz-Signature=SECRET"
                ),
                "timeout": "Authorization: Bearer TOKEN",
            },
        )

        log_message = mock_warning.call_args.args[0]
        self.assertIn("method=POST", log_message)
        self.assertIn("endpoint=evaluations/safe-endpoint", log_message)
        self.assertIn("timeout=(5, 30)", log_message)
        self.assertNotIn("LEAKY", log_message)
        self.assertNotIn("SECRET", log_message)
        self.assertNotIn("TOKEN", log_message)


if __name__ == "__main__":
    unittest.main()
