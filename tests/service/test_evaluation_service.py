from typing import Any, Dict
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from uuid import uuid4

from requests import Response

from podonos.common.enum import EvalType, Language, QuestionFileType
from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.file import Audio
from podonos.service.evaluation_service import EvaluationService

from tests.core.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV


class TestEvaluationService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = EvaluationService(self.mock_api_client)
        self.sample_eval_config = EvalConfig(
            name="test_eval",
            type=EvalType.NMOS.value,
            lan=Language.ENGLISH_AMERICAN.value,
            granularity=0.5,
            num_eval=10,
        )
        self.test_audio = Audio(
            path=TESTDATA_SPEECH_TWO_CH1_WAV,
            name="speech_two_ch1.wav",
            remote_object_name="remote/speech_two_ch1.wav",
            script="test script",
            tags=["test"],
            model_tag="test_model",
            is_ref=False,
            group="test_group",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

    def test_should_create_evaluation_successfully(self):
        # Given
        expected_eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": expected_eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 10,
            "status": "ACTIVE",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # When
        evaluation = self.service.create(self.sample_eval_config)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(evaluation.id, expected_eval_id)
        self.assertEqual(evaluation.status, "ACTIVE")

    def test_should_raise_error_on_creation_failure(self):
        # Given
        error_response = Mock(status_code=500)
        error_response.raise_for_status.side_effect = HTTPError(
            "Failed to create evaluation", 500
        )
        self.mock_api_client.post.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create(self.sample_eval_config)
        self.assertEqual(
            context.exception.args[0],
            "Failed to create the evaluation: Failed to create evaluation",
        )

    def test_should_get_evaluation_successfully(self):
        # Given
        eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": "test_internal",
            "description": "Test description",
            "batch_size": 10,
            "status": "active",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")

    def test_should_get_evaluation_with_minimal_data(self):
        # Given
        eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": None,
            "description": None,
            "batch_size": 10,
            "status": "active",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")
        self.assertIsNone(evaluation.internal_name)
        self.assertIsNone(evaluation.description)

    def test_get_evaluation_passes_timeout_and_context_when_provided(self):
        # Given
        eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": eval_id,
            "title": "Test Evaluation",
            "internal_name": None,
            "description": None,
            "batch_size": 10,
            "status": "active",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # When
        evaluation = self.service.get_evaluation(
            eval_id,
            timeout=(7, 77),
            context={"operation": "resume_evaluation"},
        )

        # Then
        self.mock_api_client.get.assert_called_once_with(
            f"evaluations/{eval_id}",
            timeout=(7, 77),
            context={
                "operation": "resume_evaluation",
                "endpoint": f"evaluations/{eval_id}",
                "evaluation_id": eval_id,
            },
        )
        self.assertEqual(evaluation.id, eval_id)

    def test_should_handle_get_evaluation_failure(self):
        # Given
        eval_id = str(uuid4())
        error_response = Mock(status_code=404)
        error_response.raise_for_status.side_effect = HTTPError(
            "Failed to get evaluation", 404
        )
        self.mock_api_client.get.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_evaluation(eval_id)
        self.assertEqual(
            context.exception.args[0],
            "Failed to get evaluation: Failed to get evaluation",
        )

    def test_should_create_evaluation_files_successfully(self):
        # Given
        eval_id = str(uuid4())
        expected_response = {"message": "Files created successfully"}
        self.mock_api_client.put.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # When
        self.service.create_evaluation_files(eval_id, [self.test_audio])

        # Then
        self.mock_api_client.put.assert_called_once()

    def test_create_evaluation_files_passes_api_timeout_and_context(self):
        # Given
        eval_id = str(uuid4())
        self.mock_api_client.put.return_value = Mock(status_code=200)

        # When
        self.service.create_evaluation_files(
            eval_id,
            [self.test_audio],
            timeout=(7, 77),
            context={"batch_index": 3},
        )

        # Then
        self.mock_api_client.put.assert_called_once()
        _, kwargs = self.mock_api_client.put.call_args
        self.assertEqual(kwargs["timeout"], (7, 77))
        self.assertEqual(kwargs["context"]["evaluation_id"], eval_id)
        self.assertEqual(kwargs["context"]["file_count"], 1)
        self.assertEqual(kwargs["context"]["batch_index"], 3)

    def test_should_handle_create_evaluation_files_failure(self):
        # Given
        eval_id = str(uuid4())
        self.mock_api_client.put.side_effect = Exception(
            "Failed to create evaluation files"
        )

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_evaluation_files(eval_id, [self.test_audio])
        self.assertIn("Failed to create evaluation files", str(context.exception))

    def test_get_evaluation_list_success(self):
        # Given
        evaluation_id = str(uuid4())
        expected_evaluations = [
            {
                "id": evaluation_id,
                "title": "Evaluation 1",
                "internal_name": "Audio Evaluation",
                "description": "This is a test evaluation",
                "batch_size": 10,
                "status": "ACTIVE",
                "created_time": "2021-01-01T00:00:00Z",
                "updated_time": "2021-01-01T00:00:00Z",
            }
        ]
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_evaluations
        )

        # When
        evaluations = self.service.get_evaluation_list()

        # Then
        self.mock_api_client.get.assert_called_once_with("evaluations")
        self.assertEqual(evaluations[0]["id"], evaluation_id)
        self.assertEqual(evaluations[0]["title"], "Evaluation 1")
        self.assertEqual(evaluations[0]["internal_name"], "Audio Evaluation")
        self.assertEqual(evaluations[0]["description"], "This is a test evaluation")
        self.assertEqual(evaluations[0]["batch_size"], 10)
        self.assertEqual(evaluations[0]["status"], "ACTIVE")

    def test_get_stats_dict_by_id_success(self):
        # Given
        evaluation_id = str(uuid4())
        expected_stats = [
            {
                "files": [
                    {
                        "name": "file1.wav",
                        "model_tag": "model1",
                        "tags": ["tag1", "tag2"],
                        "type": "A",
                    }
                ],
                "question": {"title": "question1", "order": 1},
                "mean": 0.5,
                "median": 0.5,
                "std": 0.1,
                "sem": 0.05,
                "ci_95": 0.2,
            }
        ]
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_stats
        )

        # When
        stats = self.service.get_stats_json_by_id(evaluation_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(
            f"evaluations/{evaluation_id}/stats?group-by=question"
        )
        self.assertEqual(stats, expected_stats)

    @patch("os.makedirs")
    @patch("builtins.open", create=True)
    @patch("json.dump")
    def test_download_evaluation_files_by_evaluation_id_success(
        self, mock_json_dump: Mock, mock_open: Mock, mock_makedirs: Mock
    ):
        # Given
        evaluation_id = str(uuid4())
        eval_file_1_id = str(uuid4())
        eval_file_2_id = str(uuid4())
        file_meta_1_id = str(uuid4())
        file_meta_2_id = str(uuid4())
        output_dir = "./output"
        expected_response = {
            "evaluation_id": evaluation_id,
            "cookie": {
                "CloudFront-Policy": "test_policy",
                "CloudFront-Signature": "test_signature",
                "CloudFront-Key-Pair-Id": "test_key_pair_id",
            },
            "files": [
                {
                    "evaluation_file_id": eval_file_1_id,
                    "file_meta_id": file_meta_1_id,
                    "original_name": "file1.wav",
                    "original_url": "https://files.podonos.com/file1.wav",
                    "model_tag": "model1",
                    "tags": ["tag1", "tag2"],
                },
                {
                    "evaluation_file_id": eval_file_2_id,
                    "file_meta_id": file_meta_2_id,
                    "original_name": "file2.wav",
                    "original_url": "https://assets.podonosapi.com/file2.wav",
                    "model_tag": "model2",
                    "tags": ["tag3", "tag4"],
                },
            ],
        }

        # Mock API responses
        self.mock_api_client.get.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # Mock external_get responses for file downloads
        mock_file_response1 = Mock(
            status_code=200,
            content=b"test_content1",
            headers={"Content-Type": "audio/wav"},
        )
        mock_file_response2 = Mock(
            status_code=200,
            content=b"test_content2",
            headers={"Content-Type": "audio/wav"},
        )
        self.mock_api_client.external_get.side_effect = [
            mock_file_response1,
            mock_file_response2,
        ]

        # Mock file operations
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # When
        with patch.object(self.service, "_write_download_file") as mock_write_download:
            result = self.service.download_evaluation_files_by_evaluation_id(
                evaluation_id, output_dir
            )

        # Then
        self.mock_api_client.get.assert_called_once_with(
            f"evaluation-files/download?evaluation-id={evaluation_id}"
        )
        self.assertEqual(self.mock_api_client.external_get.call_count, 2)
        for call in self.mock_api_client.external_get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
        self.assertEqual(mock_write_download.call_count, 3)
        self.assertEqual(result, "Files downloaded successfully.")

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_upload_evaluation_file_successfully(
        self, mock_access: Mock, mock_isfile: Mock
    ):
        # Given
        url = "https://presigned-url.com/upload"
        path = "/tmp/test.wav"

        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        # Mock the file operations
        with patch("builtins.open", create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file

            mock_response = Mock(status_code=200)
            self.mock_api_client.external_put.return_value = mock_response

            # When
            response = self.service.upload_evaluation_file(url, path)

            # Then
            self.mock_api_client.external_put.assert_called_once_with(
                url,
                data=mock_file,
                headers={"Content-Type": "audio/wav"},
                timeout=(10, 300),
                context={"file_count": 1},
            )
            self.assertEqual(response, mock_response)
            mock_response.raise_for_status.assert_called_once()

    @patch("os.path.isfile")
    @patch("os.access")
    def test_upload_evaluation_file_raises_on_presigned_http_error(
        self, mock_access: Mock, mock_isfile: Mock
    ):
        url = "https://presigned-url.com/upload"
        path = "/tmp/test.wav"
        mock_isfile.return_value = True
        mock_access.return_value = True

        with patch("builtins.open", create=True):
            mock_response = Mock(status_code=403)
            mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
            self.mock_api_client.external_put.return_value = mock_response

            with self.assertRaises(HTTPError) as context:
                self.service.upload_evaluation_file(url, path)

        self.assertIn("Failed to Upload File", str(context.exception))
        self.assertIn("403 Forbidden", str(context.exception))
        self.assertNotIn("test.wav", str(context.exception))

    def test_should_upload_session_json_successfully(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data: Dict[str, Any] = {"key": "value", "files": []}
        headers = {"Content-Type": "application/json"}

        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response

        # When
        response = self.service.put_session_json(url, data, headers)

        # Then
        self.mock_api_client.external_put.assert_called_once_with(
            url,
            json_data=data,
            headers=headers,
            timeout=(10, 300),
            context=None,
        )
        self.assertEqual(response, mock_response)
        mock_response.raise_for_status.assert_called_once()

    def test_should_upload_session_json_without_headers(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data: Dict[str, Any] = {"key": "value", "files": []}

        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response

        # When
        response = self.service.put_session_json(url, data)

        # Then
        self.mock_api_client.external_put.assert_called_once_with(
            url,
            json_data=data,
            headers=None,
            timeout=(10, 300),
            context=None,
        )
        self.assertEqual(response, mock_response)
        mock_response.raise_for_status.assert_called_once()

    def test_put_session_json_raises_on_presigned_http_error(self):
        url = "https://presigned-url.com/session.json"
        data: Dict[str, Any] = {"key": "value", "files": []}
        mock_response = Mock(status_code=403)
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        self.mock_api_client.external_put.return_value = mock_response

        with self.assertRaises(HTTPError) as context:
            self.service.put_session_json(url, data)

        self.assertIn("Failed to Upload JSON", str(context.exception))
        self.assertIn("403 Forbidden", str(context.exception))

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_handle_upload_evaluation_file_failure(
        self, mock_access: Mock, mock_isfile: Mock
    ):
        # Given
        url = "https://presigned-url.com/upload"
        path = "/tmp/test.wav"

        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        with patch("builtins.open", create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file

            error_response = Mock()
            error_response.status_code = 500
            self.mock_api_client.external_put.side_effect = Exception("Upload failed")

            # When/Then
            with self.assertRaises(HTTPError) as context:
                self.service.upload_evaluation_file(url, path)
            self.assertIn("Failed to Upload File", str(context.exception))
            self.assertNotIn("test.wav", str(context.exception))

    def test_should_handle_put_session_json_failure(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data = {"key": "value"}

        self.mock_api_client.external_put.side_effect = Exception("JSON upload failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.put_session_json(url, data)
        self.assertIn("Failed to Upload JSON", str(context.exception))

    @patch("podonos.service.evaluation_service.log.debug")
    def test_put_session_json_does_not_log_or_raise_payload_values(self, mock_debug: Mock):
        # Given
        url = "https://presigned-url.com/session.json"
        data = {
            "name": "sensitive-eval-name",
            "files": [
                {
                    "group_id": "group-1",
                    "audios": [
                        {
                            "remote_name": "customer/private/audio.wav",
                            "script": "customer transcript should stay private",
                            "tag": ["vip-customer-tag"],
                            "meta_data": {"account": "secret-account"},
                        }
                    ],
                }
            ],
        }
        self.mock_api_client.external_put.side_effect = Exception(
            "JSON upload failed for "
            "https://bucket.s3.amazonaws.com/session.json?X-Amz-Signature=SECRET"
        )

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.put_session_json(url, data)

        debug_output = " ".join(str(call.args[0]) for call in mock_debug.call_args_list)
        error_message = str(context.exception)
        combined = f"{debug_output} {error_message}"
        self.assertIn("file_group_count", combined)
        self.assertIn("audio_count", combined)
        self.assertNotIn("customer transcript should stay private", combined)
        self.assertNotIn("customer/private/audio.wav", combined)
        self.assertNotIn("vip-customer-tag", combined)
        self.assertNotIn("secret-account", combined)
        self.assertNotIn("X-Amz-Signature=SECRET", combined)
        self.assertIn("[REDACTED]", combined)

    def test_should_upload_session_json_with_audio_groups(self):
        # Given
        evaluation_id = str(uuid4())
        config = self.sample_eval_config
        mock_audio_group = Mock()
        mock_audio_group.to_dict.return_value = {"group": "test", "files": []}
        audio_groups = [mock_audio_group]  # type: ignore

        # Mock the presigned URL response
        mock_presigned_response = Mock()
        mock_presigned_response.text = '"https://presigned-url.com/session.json"'
        self.mock_api_client.put.return_value = mock_presigned_response

        # Mock the external put for session JSON
        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response

        # When
        self.service.upload_session_json(evaluation_id, config, audio_groups)  # type: ignore

        # Then
        _, presigned_kwargs = self.mock_api_client.put.call_args
        self.assertEqual(presigned_kwargs["timeout"], config.api_timeout)
        _, upload_kwargs = self.mock_api_client.external_put.call_args
        self.assertEqual(upload_kwargs["timeout"], config.upload_timeout)
        self.assertEqual(upload_kwargs["context"]["evaluation_id"], evaluation_id)

    def test_download_path_helpers_sanitize_model_tag_and_enforce_output_root(self):
        with tempfile.TemporaryDirectory() as output_dir:
            safe_segment = self.service._safe_download_path_segment("../../outside")
            self.assertEqual(safe_segment, "outside")

            safe_path = self.service._safe_output_path(
                output_dir, safe_segment, "file.wav"
            )
            self.assertEqual(
                os.path.commonpath([os.path.abspath(output_dir), safe_path]),
                os.path.abspath(output_dir),
            )

            with self.assertRaises(ValueError):
                self.service._safe_output_path(output_dir, "..", "outside.wav")

    @unittest.skipIf(os.name == "nt", "POSIX symlink check")
    def test_write_download_file_rejects_symlink_parent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = os.path.join(temp_dir, "output")
            outside_dir = os.path.join(temp_dir, "outside")
            os.makedirs(output_dir)
            os.makedirs(outside_dir)
            os.symlink(outside_dir, os.path.join(output_dir, "model"))
            file_path = os.path.join(output_dir, "model", "file.wav")

            with self.assertRaises(ValueError):
                self.service._write_download_file(
                    file_path, b"audio", output_dir
                )

            self.assertFalse(os.path.exists(os.path.join(outside_dir, "file.wav")))

    def test_download_errors_are_redacted(self):
        evaluation_id = str(uuid4())
        self.mock_api_client.get.side_effect = Exception(
            "download failed Cookie: session=SECRET "
            "CloudFront-Signature=SIGNATURE"
        )

        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(HTTPError) as context:
                self.service.download_evaluation_files_by_evaluation_id(
                    evaluation_id, output_dir
                )

        message = str(context.exception)
        self.assertNotIn("SECRET", message)
        self.assertNotIn("SIGNATURE", message)
        self.assertIn("[REDACTED]", message)

    def test_download_rejects_untrusted_original_url_before_sending_cookies(self):
        evaluation_id = str(uuid4())
        self.mock_api_client.get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "cookie": {"CloudFront-Signature": "SECRET"},
                "files": [
                    {
                        "evaluation_file_id": "file-id",
                        "file_meta_id": "meta-id",
                        "original_name": "file.wav",
                        "original_url": "http://attacker.example/file.wav",
                        "model_tag": "model",
                        "tags": [],
                    }
                ],
            },
        )

        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(HTTPError) as context:
                self.service.download_evaluation_files_by_evaluation_id(
                    evaluation_id, output_dir
                )

        self.mock_api_client.external_get.assert_not_called()
        self.assertNotIn("SECRET", str(context.exception))

    def test_download_rejects_unowned_cloudfront_host_by_default(self):
        with self.assertRaises(ValueError):
            self.service._validate_download_original_url(
                "https://d111111abcdef8.cloudfront.net/file.wav"
            )

    def test_download_allows_explicit_configured_host(self):
        with patch.dict(
            os.environ,
            {"PODONOS_DOWNLOAD_ALLOWED_HOSTS": "d111111abcdef8.cloudfront.net"},
        ):
            self.assertEqual(
                self.service._validate_download_original_url(
                    "https://d111111abcdef8.cloudfront.net/file.wav"
                ),
                "https://d111111abcdef8.cloudfront.net/file.wav",
            )

    def test_download_rejects_untrusted_redirect_without_following(self):
        evaluation_id = str(uuid4())
        self.mock_api_client.get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "cookie": {"CloudFront-Signature": "SECRET"},
                "files": [
                    {
                        "evaluation_file_id": "file-id",
                        "file_meta_id": "meta-id",
                        "original_name": "file.wav",
                        "original_url": "https://files.podonos.com/file.wav",
                        "model_tag": "model",
                        "tags": [],
                    }
                ],
            },
        )
        redirect_response = Mock(
            status_code=302,
            headers={"Location": "https://attacker.example/file.wav"},
        )
        redirect_response.raise_for_status.side_effect = Exception("302 redirect")
        self.mock_api_client.external_get.return_value = redirect_response

        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(HTTPError):
                self.service.download_evaluation_files_by_evaluation_id(
                    evaluation_id, output_dir
                )

        self.mock_api_client.external_get.assert_called_once()
        self.assertFalse(self.mock_api_client.external_get.call_args.kwargs["allow_redirects"])

    def test_download_rejects_real_302_response_without_writing_file(self):
        evaluation_id = str(uuid4())
        self.mock_api_client.get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "cookie": {"CloudFront-Signature": "SECRET"},
                "files": [
                    {
                        "evaluation_file_id": "file-id",
                        "file_meta_id": "meta-id",
                        "original_name": "file.wav",
                        "original_url": "https://files.podonos.com/file.wav",
                        "model_tag": "model",
                        "tags": [],
                    }
                ],
            },
        )
        redirect_response = Response()
        redirect_response.status_code = 302
        redirect_response.headers["Location"] = "https://attacker.example/file.wav"
        redirect_response.headers["Content-Type"] = "audio/wav"
        redirect_response._content = b"redirect body"
        self.mock_api_client.external_get.return_value = redirect_response

        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaises(HTTPError) as context:
                self.service.download_evaluation_files_by_evaluation_id(
                    evaluation_id, output_dir
                )
            self.assertEqual(os.listdir(output_dir), [])

        self.assertIn("non-success status", str(context.exception))
        self.assertNotIn("SECRET", str(context.exception))

    def test_should_handle_upload_session_json_failure(self):
        # Given
        evaluation_id = str(uuid4())
        config = self.sample_eval_config
        mock_audio_group = Mock()
        mock_audio_group.to_dict.return_value = {"group": "test", "files": []}
        audio_groups = [mock_audio_group]  # type: ignore

        self.mock_api_client.put.side_effect = Exception("Failed to get presigned URL")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_session_json(evaluation_id, config, audio_groups)  # type: ignore
        self.assertIn("Failed to upload session JSON", str(context.exception))

    def test_should_get_presigned_url_successfully(self):
        # Given
        evaluation_id = str(uuid4())
        remote_object_name = "test.wav"
        expected_url = "https://presigned-url.com/upload"

        mock_response = Mock(status_code=200, text=f'"{expected_url}"')
        self.mock_api_client.put.return_value = mock_response

        # When
        result = self.service.get_presigned_url(evaluation_id, remote_object_name)

        # Then
        self.mock_api_client.put.assert_called_once_with(
            f"evaluations/{evaluation_id}/uploading-presigned-url",
            data={"uploaded_file_name": remote_object_name},
            timeout=(5, 30),
            context={
                "endpoint": f"evaluations/{evaluation_id}/uploading-presigned-url",
                "evaluation_id": evaluation_id,
                "file_count": 1,
            },
        )
        self.assertEqual(result, expected_url)

    def test_should_handle_get_presigned_url_failure(self):
        # Given
        evaluation_id = str(uuid4())
        remote_object_name = "test.wav"

        self.mock_api_client.put.side_effect = Exception("Failed to get presigned URL")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_presigned_url(evaluation_id, remote_object_name)
        self.assertIn("Failed to get presigned URL", str(context.exception))

    def test_should_create_evaluation_with_en_in_language(self):
        """Test creating evaluation with en-in language"""
        # Given
        expected_eval_id = str(uuid4())
        current_time = datetime.now(timezone.utc)
        expected_response = {
            "id": expected_eval_id,
            "title": "Test EN-IN Evaluation",
            "internal_name": "test_en_internal",
            "description": "Test description for Indian English",
            "batch_size": 10,
            "status": "ACTIVE",
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # Create config with en-in language
        en_in_eval_config = EvalConfig(
            name="test_en_in_eval",
            type=EvalType.NMOS.value,
            lan=Language.ENGLISH_INDIA.value,
            granularity=0.5,
            num_eval=10,
        )

        # When
        evaluation = self.service.create(en_in_eval_config)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(evaluation.id, expected_eval_id)
        self.assertEqual(evaluation.status, "ACTIVE")

    def test_should_create_evaluation_files_with_en_in_language_context(self):
        """Test creating evaluation files with en-in language context"""
        # Given
        eval_id = str(uuid4())
        expected_response = {
            "message": "Files created successfully for Indian English evaluation"
        }
        self.mock_api_client.put.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        # Create test audio with en-in context
        en_in_test_audio = Audio(
            path=TESTDATA_SPEECH_TWO_CH1_WAV,
            name="speech_en_in_ch1.wav",
            remote_object_name="remote/speech_en_in_ch1.wav",
            script="test script for Indian English",
            tags=["test", "en-in"],
            model_tag="test_model_en_in",
            is_ref=False,
            group="test_group_en_in",
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )

        # When
        self.service.create_evaluation_files(eval_id, [en_in_test_audio])

        # Then
        self.mock_api_client.put.assert_called_once()

    def test_should_get_presigned_url_with_en_in_language_context(self):
        """Test getting presigned URL with en-in language context"""
        # Given
        evaluation_id = str(uuid4())
        remote_object_name = "test_en_in.wav"
        expected_url = "https://presigned-url.com/upload-en-in"

        mock_response = Mock(status_code=200, text=f'"{expected_url}"')
        self.mock_api_client.put.return_value = mock_response

        # When
        result = self.service.get_presigned_url(evaluation_id, remote_object_name)

        # Then
        self.mock_api_client.put.assert_called_once_with(
            f"evaluations/{evaluation_id}/uploading-presigned-url",
            data={"uploaded_file_name": remote_object_name},
            timeout=(5, 30),
            context={
                "endpoint": f"evaluations/{evaluation_id}/uploading-presigned-url",
                "evaluation_id": evaluation_id,
                "file_count": 1,
            },
        )
        self.assertEqual(result, expected_url)

    def test_update_specific_fields_calls_patch(self):
        """Test update_specific_fields sends PATCH request with correct payload"""
        # Given
        eval_id = str(uuid4())
        payload: Dict[str, Any] = {
            "id": eval_id,
            "language": "en-us",
            "build_process": "FILE_UPLOAD",
            "evaluation_type": "SPEECH_RANKING",
            "batch_size": 3,
            "meta_data": {},
        }

        mock_response = Mock(status_code=200)
        self.mock_api_client.patch.return_value = mock_response

        # When
        self.service.update_specific_fields(eval_id, payload)

        # Then
        self.mock_api_client.patch.assert_called_once_with(
            f"evaluations/{eval_id}/specific-fields", data=payload
        )

    def test_update_specific_fields_passes_timeout_and_context_when_provided(self):
        """Test update_specific_fields forwards explicit timeout and retry context"""
        # Given
        eval_id = str(uuid4())
        payload: Dict[str, Any] = {
            "id": eval_id,
            "language": "en-us",
            "build_process": "FILE_UPLOAD",
            "evaluation_type": "SPEECH_RANKING",
            "batch_size": 3,
            "meta_data": {},
        }

        mock_response = Mock(status_code=200)
        self.mock_api_client.patch.return_value = mock_response

        # When
        self.service.update_specific_fields(
            eval_id,
            payload,
            timeout=(9, 99),
            context={"operation": "ranking_batch_size_resolution"},
        )

        # Then
        self.mock_api_client.patch.assert_called_once_with(
            f"evaluations/{eval_id}/specific-fields",
            data=payload,
            timeout=(9, 99),
            context={
                "operation": "ranking_batch_size_resolution",
                "endpoint": f"evaluations/{eval_id}/specific-fields",
                "evaluation_id": eval_id,
            },
        )

    def test_update_specific_fields_handles_failure(self):
        """Test update_specific_fields handles failure correctly"""
        # Given
        eval_id = str(uuid4())
        payload: Dict[str, Any] = {
            "id": eval_id,
            "language": "en-us",
            "build_process": "FILE_UPLOAD",
            "evaluation_type": "SPEECH_RANKING",
            "batch_size": 3,
            "meta_data": {},
        }

        self.mock_api_client.patch.side_effect = Exception("Failed to patch")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.update_specific_fields(eval_id, payload)
        self.assertIn(
            "Failed to update evaluation specific fields", str(context.exception)
        )

    def test_verify_files_success(self):
        # Given
        eval_id = str(uuid4())
        expected_response = {
            "all_verified": True,
            "verified_count": 1,
            "failed_count": 0,
            "results": [
                {
                    "uploaded_file_name": "remote/speech_two_ch1.wav",
                    "verified": True,
                    "file_meta_id": str(uuid4()),
                    "error": None,
                }
            ],
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        self.test_audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # When
        result = self.service.verify_files(eval_id, [self.test_audio])

        # Then
        self.mock_api_client.post.assert_called_once()
        _, kwargs = self.mock_api_client.post.call_args
        self.assertEqual(kwargs["timeout"], (5, 120))
        self.assertEqual(kwargs["context"]["endpoint"], f"evaluations/{eval_id}/files/verify")
        self.assertEqual(kwargs["context"]["evaluation_id"], eval_id)
        self.assertEqual(kwargs["context"]["file_count"], 1)
        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, 1)
        self.assertEqual(result.failed_count, 0)

    def test_verify_files_passes_custom_timeout_and_context(self):
        # Given
        eval_id = str(uuid4())
        expected_response = {
            "all_verified": True,
            "verified_count": 1,
            "failed_count": 0,
            "results": [
                {
                    "uploaded_file_name": "remote/speech_two_ch1.wav",
                    "verified": True,
                    "file_meta_id": str(uuid4()),
                    "error": None,
                }
            ],
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )
        self.test_audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # When
        self.service.verify_files(
            eval_id,
            [self.test_audio],
            timeout=(7, 180),
            context={"batch_index": 2, "batch_size": 1},
        )

        # Then
        _, kwargs = self.mock_api_client.post.call_args
        self.assertEqual(kwargs["timeout"], (7, 180))
        self.assertEqual(kwargs["context"]["batch_index"], 2)
        self.assertEqual(kwargs["context"]["batch_size"], 1)

    def test_verify_files_partial_failure(self):
        # Given
        eval_id = str(uuid4())
        expected_response = {
            "all_verified": False,
            "verified_count": 0,
            "failed_count": 1,
            "results": [
                {
                    "uploaded_file_name": "remote/speech_two_ch1.wav",
                    "verified": False,
                    "file_meta_id": str(uuid4()),
                    "error": {
                        "code": "FILE_MD5_MISMATCH",
                        "message": "MD5 hash mismatch",
                        "expected": "AA259hLYqLX6hjV81ve5Cg==",
                        "actual": "rqXc34Ir5GRBYFV++6Traw==",
                    },
                }
            ],
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=200, json=lambda: expected_response
        )

        self.test_audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # When
        result = self.service.verify_files(eval_id, [self.test_audio])

        # Then
        self.assertFalse(result.all_verified)
        self.assertEqual(result.failed_count, 1)
        self.assertIsNotNone(result.results[0].error)
        self.assertEqual(result.results[0].error.code, "FILE_MD5_MISMATCH")

    def test_verify_files_handles_failure(self):
        # Given
        eval_id = str(uuid4())
        self.mock_api_client.post.side_effect = Exception("Verify failed")

        self.test_audio.set_integrity_info("AA259hLYqLX6hjV81ve5Cg==", 17920)

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.verify_files(eval_id, [self.test_audio])
        self.assertIn("Failed to verify evaluation files", str(context.exception))

    def test_upload_evaluation_file_passes_custom_timeout(self):
        # Given
        response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = response

        # When
        result = self.service.upload_evaluation_file(
            "https://example.com/presigned?X-Amz-Signature=secret",
            TESTDATA_SPEECH_TWO_CH1_WAV,
            timeout=(11, 222),
            context={"evaluation_id": "eval-id"},
        )

        # Then
        self.assertEqual(result, response)
        _, kwargs = self.mock_api_client.external_put.call_args
        self.assertEqual(kwargs["timeout"], (11, 222))
        self.assertEqual(kwargs["context"]["evaluation_id"], "eval-id")
        self.assertEqual(kwargs["context"]["file_count"], 1)

    def test_process_files_success(self):
        # Given
        eval_id = str(uuid4())
        file_meta_ids = [str(uuid4()), str(uuid4())]
        expected_response = {
            "processing_count": 2,
            "file_meta_ids": file_meta_ids,
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=202, json=lambda: expected_response
        )

        # When
        result = self.service.process_files(eval_id, file_meta_ids)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(result.processing_count, 2)
        self.assertEqual(result.file_meta_ids, file_meta_ids)

    def test_process_files_without_ids(self):
        # Given
        eval_id = str(uuid4())
        expected_response = {
            "processing_count": 5,
            "file_meta_ids": [str(uuid4()) for _ in range(5)],
        }
        self.mock_api_client.post.return_value = Mock(
            status_code=202, json=lambda: expected_response
        )

        # When
        result = self.service.process_files(eval_id)

        # Then
        self.mock_api_client.post.assert_called_once_with(
            f"evaluations/{eval_id}/files/process",
            data={},
            timeout=(5, 30),
            context={
                "endpoint": f"evaluations/{eval_id}/files/process",
                "evaluation_id": eval_id,
                "file_count": 0,
            },
        )
        self.assertEqual(result.processing_count, 5)

    def test_process_files_handles_failure(self):
        # Given
        eval_id = str(uuid4())
        self.mock_api_client.post.side_effect = Exception("Process failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.process_files(eval_id)
        self.assertIn("Failed to trigger file processing", str(context.exception))


if __name__ == "__main__":
    unittest.main()
