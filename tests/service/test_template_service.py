import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, Mock, patch
from typing import Any, Dict

from podonos.core.api import APIClient
from podonos.core.template import Template
from podonos.core.types import TemplateOption, TemplateQuestion
from podonos.common.enum import QuestionResponseCategory, QuestionUsageType
from podonos.service.template_service import TemplateService

from tests.core.test_audio import TESTDATA_SPEECH_CH1_MP3
from podonos.common.exception import HTTPError
from podonos.core.query import TYPE_OF_REFERENCE_FILES


class TestTemplateService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = TemplateService(self.mock_api_client)
        self.template_id = "test_template_id"
        self.question_id = "test_question_id"
        self.option_id = "test_option_id"
        self.file_path = TESTDATA_SPEECH_CH1_MP3
        self.presigned_url = "https://test_presigned_url"

        # Mock template data with all required fields
        current_time = datetime.now(timezone.utc)
        self.mock_template_data: Dict[str, Any] = {
            "id": self.template_id,
            "code": "TEST_CODE",
            "title": "Test Template",
            "description": "Test Description",
            "batch_size": 1,
            "use_annotation": False,
            "use_power_normalization": False,
            "language": "en-us",  # Language enum value
            "created_time": current_time.isoformat(),
            "updated_time": current_time.isoformat(),
            "questions": [],  # Optional field
        }

    def test_should_get_template_by_code_successfully(self):
        # Given
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: self.mock_template_data)

        # When
        template = self.service.get_template_by_code(self.template_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"templates/one?code={self.template_id}")
        self.assertIsInstance(template, Template)
        self.assertEqual(template.id, self.template_id)

    def test_should_create_template_questions_successfully(self):
        # Given
        evaluation_id = "test_eval_id"
        template_questions = [
            TemplateQuestion(title="Test Question", response_category=QuestionResponseCategory.CHOICE_ONE, usage_type=QuestionUsageType.SCORE)
        ]

        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: [{"id": "question_id"}])

        # When
        self.service.create_template_questions_by_evaluation_id_and_questions(evaluation_id, template_questions)

        # Then
        self.mock_api_client.put.assert_called_once_with(
            "template-questions/bulk", data={"evaluation_id": evaluation_id, "questions": [q.to_create_dict() for q in template_questions]}
        )

    def test_should_create_template_options_successfully(self):
        # Given
        question_id = "test_question_id"
        template_options = [TemplateOption(value="Option 1"), TemplateOption(value="Option 2")]

        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: [{"id": "option_id"}])

        # When
        self.service.create_template_options_by_question_id_and_options(question_id, template_options)

        # Then
        self.mock_api_client.put.assert_called_once()

    def test_should_get_presigned_url_by_template_question_id_successfully(self):
        # Given
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: {"presigned_url": self.presigned_url})

        # When
        self.service.get_presigned_url_by_template_question_id(self.question_id)

        # Then
        self.mock_api_client.post.assert_called_once_with(f"template-questions/{self.question_id}/reference-uri", data={})

    def test_should_get_presigned_url_by_template_option_id_successfully(self):
        # Given
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: {"presigned_url": self.presigned_url})

        # When
        self.service.get_presigned_url_by_template_option_id(self.option_id)

        # Then
        self.mock_api_client.post.assert_called_once_with(f"template-options/{self.option_id}/reference-uri", data={})

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_upload_reference_file_by_url_and_file_path_successfully(self, mock_access: Mock, mock_isfile: Mock):
        # Given
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response

        # When
        self.service.upload_reference_file_by_url_and_file_path(self.presigned_url, self.file_path)

        # Then
        self.mock_api_client.external_put.assert_called_once_with(self.presigned_url, data=ANY)

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_handle_upload_reference_file_failure_with_question_id(self, mock_access: Mock, mock_isfile: Mock):
        # Given
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        self.mock_api_client.external_put.side_effect = Exception("Upload failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_file_by_url_and_file_path(self.presigned_url, self.file_path, question_id=self.question_id)

        self.assertIn("Failed to upload reference file by question id", str(context.exception))
        self.mock_api_client.delete.assert_called_once_with(f"template-questions/{self.question_id}/reference-uri")

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_handle_upload_reference_file_failure_with_option_id(self, mock_access: Mock, mock_isfile: Mock):
        # Given
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        self.mock_api_client.external_put.side_effect = Exception("Upload failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_file_by_url_and_file_path(self.presigned_url, self.file_path, option_id=self.option_id)

        self.assertIn("Failed to upload reference file by option id", str(context.exception))
        self.mock_api_client.delete.assert_called_once_with(f"template-options/{self.option_id}/reference-uri")

    @patch("os.path.isfile")
    @patch("os.access")
    def test_should_handle_upload_reference_file_failure_without_ids(self, mock_access: Mock, mock_isfile: Mock):
        # Given
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True

        self.mock_api_client.external_put.side_effect = Exception("Upload failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_file_by_url_and_file_path(self.presigned_url, self.file_path)

        self.assertIn("Failed to upload reference file by url", str(context.exception))

    def test_should_handle_get_template_failure(self):
        # Given
        self.mock_api_client.get.side_effect = Exception("API call failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_template_by_code(self.template_id)
        self.assertIn("Failed to get template by id", str(context.exception))

    def test_should_handle_create_template_questions_failure(self):
        # Given
        evaluation_id = "test_eval_id"
        template_questions = [
            TemplateQuestion(title="Test Question", response_category=QuestionResponseCategory.CHOICE_ONE, usage_type=QuestionUsageType.SCORE)
        ]

        self.mock_api_client.put.side_effect = Exception("API call failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_template_questions_by_evaluation_id_and_questions(evaluation_id, template_questions)
        self.assertIn("Failed to create template questions by evaluation id", str(context.exception))

    def test_should_handle_create_template_options_failure(self):
        # Given
        question_id = "test_question_id"
        template_options = [TemplateOption(value="Option 1"), TemplateOption(value="Option 2")]

        self.mock_api_client.put.side_effect = Exception("API call failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_template_options_by_question_id_and_options(question_id, template_options)
        self.assertIn("Failed to create template options by question id", str(context.exception))

    def test_should_handle_get_presigned_url_question_failure(self):
        # Given
        self.mock_api_client.post.side_effect = Exception("API call failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_presigned_url_by_template_question_id(self.question_id)
        self.assertIn("Failed to get presigned URL for template question id", str(context.exception))

    def test_should_handle_get_presigned_url_option_failure(self):
        # Given
        self.mock_api_client.post.side_effect = Exception("API call failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_presigned_url_by_template_option_id(self.option_id)
        self.assertIn("Failed to get presigned URL for template option id", str(context.exception))

    @patch("builtins.open", create=True)
    def test_should_upload_reference_files_successfully(self, mock_open: Mock):
        # Given
        reference_files: TYPE_OF_REFERENCE_FILES = [{"path": self.file_path, "type": "audio"}, {"path": self.file_path, "type": "audio"}]

        # Mock file open
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock presigned URL responses (called twice, once for each file)
        presigned_url_1 = "https://presigned-url-1.com"
        presigned_url_2 = "https://presigned-url-2.com"
        reference_uri_1 = "s3://bucket/file1"
        reference_uri_2 = "s3://bucket/file2"

        self.mock_api_client.get.side_effect = [
            Mock(status_code=200, json=lambda: {"url": presigned_url_1, "uri": reference_uri_1}),
            Mock(status_code=200, json=lambda: {"url": presigned_url_2, "uri": reference_uri_2}),
        ]

        # Mock external_put for file uploads
        self.mock_api_client.external_put.return_value = Mock(status_code=200)

        # Mock final PUT request
        self.mock_api_client.put.return_value = Mock(status_code=200)

        # When
        self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        # Then
        # Verify GET requests for presigned URLs (called twice)
        self.assertEqual(self.mock_api_client.get.call_count, 2)
        self.mock_api_client.get.assert_any_call(f"template-questions/{self.question_id}/references/presigned-url")

        # Verify external_put for file uploads (called twice)
        self.assertEqual(self.mock_api_client.external_put.call_count, 2)

        # Verify final PUT request with references
        self.mock_api_client.put.assert_called_once()
        call_args = self.mock_api_client.put.call_args
        self.assertEqual(call_args[0][0], f"template-questions/{self.question_id}/references")
        self.assertIn("references", call_args[1]["data"])
        self.assertEqual(len(call_args[1]["data"]["references"]), 2)
        self.assertEqual(call_args[1]["data"]["references"][0]["reference_uri"], reference_uri_1)
        self.assertEqual(call_args[1]["data"]["references"][0]["type"], "audio")
        self.assertEqual(call_args[1]["data"]["references"][0]["label_text"], None)

    def test_should_handle_empty_reference_files(self) -> None:
        # Given
        reference_files: TYPE_OF_REFERENCE_FILES = []

        # When
        self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        # Then
        # Should return early without making any API calls
        self.mock_api_client.get.assert_not_called()
        self.mock_api_client.external_put.assert_not_called()
        self.mock_api_client.put.assert_not_called()

    def test_should_handle_none_reference_files(self) -> None:
        # Given
        reference_files = None

        # When
        self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        # Then
        # Should return early without making any API calls
        self.mock_api_client.get.assert_not_called()
        self.mock_api_client.external_put.assert_not_called()
        self.mock_api_client.put.assert_not_called()

    @patch("builtins.open", create=True)
    def test_should_handle_presigned_url_failure(self, mock_open: Mock):
        # Given
        reference_files: TYPE_OF_REFERENCE_FILES = [{"path": self.file_path, "type": "audio"}]

        # Mock file open
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock presigned URL failure
        self.mock_api_client.get.side_effect = Exception("Failed to get presigned URL")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        self.assertIn("Failed to upload reference files for question id", str(context.exception))
        self.mock_api_client.put.assert_not_called()

    @patch("builtins.open", create=True)
    def test_should_handle_file_upload_failure(self, mock_open: Mock):
        # Given
        reference_files: TYPE_OF_REFERENCE_FILES = [{"path": self.file_path, "type": "audio"}]

        # Mock file open
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock presigned URL response
        presigned_url = "https://presigned-url.com"
        reference_uri = "s3://bucket/file"
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: {"url": presigned_url, "uri": reference_uri})

        # Mock file upload failure
        self.mock_api_client.external_put.side_effect = Exception("Upload failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        self.assertIn("Failed to upload reference files for question id", str(context.exception))
        # Final PUT should not be called if upload fails
        self.mock_api_client.put.assert_not_called()

    @patch("builtins.open", create=True)
    def test_should_handle_final_put_request_failure(self, mock_open: Mock):
        # Given
        reference_files: TYPE_OF_REFERENCE_FILES = [{"path": self.file_path, "type": "audio"}]

        # Mock file open
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Mock presigned URL response
        presigned_url = "https://presigned-url.com"
        reference_uri = "s3://bucket/file"
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: {"url": presigned_url, "uri": reference_uri})

        # Mock successful file upload
        self.mock_api_client.external_put.return_value = Mock(status_code=200)

        # Mock final PUT request failure
        self.mock_api_client.put.side_effect = Exception("PUT request failed")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.upload_reference_files_by_url_and_file_paths(reference_files, self.question_id)

        self.assertIn("Failed to upload reference files for question id", str(context.exception))
        # Verify PUT was called
        self.mock_api_client.put.assert_called_once()


if __name__ == "__main__":
    unittest.main()
