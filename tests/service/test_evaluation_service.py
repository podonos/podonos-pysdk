import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone


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
            name="test_eval", type=EvalType.NMOS.value, lan=Language.ENGLISH_AMERICAN.value, granularity=0.5, num_eval=10
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
        expected_eval_id = "test_eval_id"
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
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.create(self.sample_eval_config)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(evaluation.id, expected_eval_id)
        self.assertEqual(evaluation.status, "ACTIVE")

    def test_should_raise_error_on_creation_failure(self):
        # Given
        error_response = Mock(status_code=500)
        error_response.raise_for_status.side_effect = HTTPError("Failed to create evaluation", 500)
        self.mock_api_client.post.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create(self.sample_eval_config)
        self.assertEqual(context.exception.args[0], "Failed to create the evaluation: Failed to create evaluation")

    def test_should_get_evaluation_successfully(self):
        # Given
        eval_id = "test_eval_id"
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
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")

    def test_should_get_evaluation_with_minimal_data(self):
        # Given
        eval_id = "test_eval_id"
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
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        evaluation = self.service.get_evaluation(eval_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{eval_id}")
        self.assertEqual(evaluation.id, eval_id)
        self.assertEqual(evaluation.title, "Test Evaluation")
        self.assertIsNone(evaluation.internal_name)
        self.assertIsNone(evaluation.description)

    def test_should_handle_get_evaluation_failure(self):
        # Given
        eval_id = "test_eval_id"
        error_response = Mock(status_code=404)
        error_response.raise_for_status.side_effect = HTTPError("Failed to get evaluation", 404)
        self.mock_api_client.get.return_value = error_response

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_evaluation(eval_id)
        self.assertEqual(context.exception.args[0], "Failed to get evaluation: Failed to get evaluation")

    def test_should_create_evaluation_files_successfully(self):
        # Given
        eval_id = "test_eval_id"
        expected_response = {"message": "Files created successfully"}
        self.mock_api_client.put.return_value = Mock(status_code=200, json=lambda: expected_response)

        # When
        self.service.create_evaluation_files(eval_id, [self.test_audio])

        # Then
        self.mock_api_client.put.assert_called_once()

    def test_should_handle_create_evaluation_files_failure(self):
        # Given
        eval_id = "test_eval_id"
        self.mock_api_client.put.side_effect = Exception("Failed to create evaluation files")

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_evaluation_files(eval_id, [self.test_audio])
        self.assertIn("Failed to create evaluation files", str(context.exception))

    def test_get_evaluation_list_success(self):
        # Given
        expected_evaluations = [
            {
                "id": "eval1",
                "title": "Evaluation 1",
                "internal_name": "Audio Evaluation",
                "description": "This is a test evaluation",
                "batch_size": 10,
                "status": "ACTIVE",
                "created_time": "2021-01-01T00:00:00Z",
                "updated_time": "2021-01-01T00:00:00Z",
            }
        ]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_evaluations)

        # When
        evaluations = self.service.get_evaluation_list()

        # Then
        self.mock_api_client.get.assert_called_once_with("evaluations")
        self.assertEqual(evaluations[0]["id"], "eval1")
        self.assertEqual(evaluations[0]["title"], "Evaluation 1")
        self.assertEqual(evaluations[0]["internal_name"], "Audio Evaluation")
        self.assertEqual(evaluations[0]["description"], "This is a test evaluation")
        self.assertEqual(evaluations[0]["batch_size"], 10)
        self.assertEqual(evaluations[0]["status"], "ACTIVE")

    def test_get_stats_dict_by_id_success(self):
        # Given
        evaluation_id = "test_evaluation_id"
        expected_stats = [
            {
                "files": [{"name": "file1.wav", "model_tag": "model1", "tags": ["tag1", "tag2"], "type": "A"}],
                "question": {"title": "question1", "order": 1},
                "mean": 0.5,
                "median": 0.5,
                "std": 0.1,
                "sem": 0.05,
                "ci_95": 0.2,
            }
        ]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_stats)

        # When
        stats = self.service.get_stats_json_by_id(evaluation_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluations/{evaluation_id}/stats?group-by=question")
        self.assertEqual(stats, expected_stats)

    @patch('os.makedirs')
    @patch('builtins.open', create=True)
    @patch('json.dump')
    def test_download_evaluation_files_by_evaluation_id_success(self, mock_json_dump, mock_open, mock_makedirs):
        # Given
        evaluation_id = "test_evaluation_id"
        output_dir = "./output"
        expected_response = {
            "evaluation_id": evaluation_id,
            "cookie": {
                "CloudFront-Policy": "test_policy",
                "CloudFront-Signature": "test_signature",
                "CloudFront-Key-Pair-Id": "test_key_pair_id"
            },
            "files": [
                {
                    "evaluation_file_id": "file1_id",
                    "file_meta_id": "meta1_id",
                    "original_name": "file1.wav",
                    "original_url": "https://example.com/file1.wav",
                    "model_tag": "model1",
                    "tags": ["tag1", "tag2"]
                },
                {
                    "evaluation_file_id": "file2_id",
                    "file_meta_id": "meta2_id",
                    "original_name": "file2.wav",
                    "original_url": "https://example.com/file2.wav",
                    "model_tag": "model2",
                    "tags": ["tag3", "tag4"]
                }
            ]
        }
        
        # Mock API responses
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: expected_response)
        
        # Mock external_get responses for file downloads
        mock_file_response1 = Mock(status_code=200, content=b"test_content1", headers={"Content-Type": "audio/wav"})
        mock_file_response2 = Mock(status_code=200, content=b"test_content2", headers={"Content-Type": "audio/wav"})
        self.mock_api_client.external_get.side_effect = [mock_file_response1, mock_file_response2]
        
        # Mock file operations
        mock_file = Mock()
        mock_open.return_value.__enter__.return_value = mock_file

        # When
        result = self.service.download_evaluation_files_by_evaluation_id(evaluation_id, output_dir)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"evaluation-files/download?evaluation-id={evaluation_id}")
        self.assertEqual(self.mock_api_client.external_get.call_count, 2)
        self.assertEqual(result, "Files downloaded successfully.")

    @patch('os.path.isfile')
    @patch('os.access')
    def test_should_upload_evaluation_file_successfully(self, mock_access, mock_isfile):
        # Given
        url = "https://presigned-url.com/upload"
        path = "/tmp/test.wav"
        
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True
        
        # Mock the file operations
        with patch('builtins.open', create=True) as mock_open:
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
                headers={"Content-Type": "audio/wav"}
            )
            self.assertEqual(response, mock_response)

    def test_should_upload_session_json_successfully(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data = {"key": "value", "files": []}
        headers = {"Content-Type": "application/json"}
        
        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response
        
        # When
        response = self.service.put_session_json(url, data, headers)
        
        # Then
        self.mock_api_client.external_put.assert_called_once_with(
            url, 
            json_data=data, 
            headers=headers
        )
        self.assertEqual(response, mock_response)

    def test_should_upload_session_json_without_headers(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data = {"key": "value", "files": []}
        
        mock_response = Mock(status_code=200)
        self.mock_api_client.external_put.return_value = mock_response
        
        # When
        response = self.service.put_session_json(url, data)
        
        # Then
        self.mock_api_client.external_put.assert_called_once_with(
            url, 
            json_data=data, 
            headers=None
        )
        self.assertEqual(response, mock_response)

    @patch('os.path.isfile')
    @patch('os.access')
    def test_should_handle_upload_evaluation_file_failure(self, mock_access, mock_isfile):
        # Given
        url = "https://presigned-url.com/upload"
        path = "/tmp/test.wav"
        
        # Mock file existence and access checks
        mock_isfile.return_value = True
        mock_access.return_value = True
        
        with patch('builtins.open', create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            error_response = Mock()
            error_response.status_code = 500
            self.mock_api_client.external_put.side_effect = Exception("Upload failed")
            
            # When/Then
            with self.assertRaises(HTTPError) as context:
                self.service.upload_evaluation_file(url, path)
            self.assertIn("Failed to Upload File", str(context.exception))

    def test_should_handle_put_session_json_failure(self):
        # Given
        url = "https://presigned-url.com/session.json"
        data = {"key": "value"}
        
        self.mock_api_client.external_put.side_effect = Exception("JSON upload failed")
        
        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.put_session_json(url, data)
        self.assertIn("Failed to Upload JSON", str(context.exception))

    def test_should_upload_session_json_with_audio_groups(self):
        # Given
        evaluation_id = "test_eval_id"
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
        self.mock_api_client.put.assert_called_once()
        self.mock_api_client.external_put.assert_called_once()

    def test_should_handle_upload_session_json_failure(self):
        # Given
        evaluation_id = "test_eval_id"
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
        evaluation_id = "test_eval_id"
        remote_object_name = "test.wav"
        expected_url = "https://presigned-url.com/upload"
        
        mock_response = Mock(status_code=200, text=f'"{expected_url}"')
        self.mock_api_client.put.return_value = mock_response
        
        # When
        result = self.service.get_presigned_url(evaluation_id, remote_object_name)
        
        # Then
        self.mock_api_client.put.assert_called_once_with(
            f"evaluations/{evaluation_id}/uploading-presigned-url",
            data={"uploaded_file_name": remote_object_name}
        )
        self.assertEqual(result, expected_url)

    def test_should_handle_get_presigned_url_failure(self):
        # Given
        evaluation_id = "test_eval_id"
        remote_object_name = "test.wav"
        
        self.mock_api_client.put.side_effect = Exception("Failed to get presigned URL")
        
        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.get_presigned_url(evaluation_id, remote_object_name)
        self.assertIn("Failed to get presigned URL", str(context.exception))

if __name__ == "__main__":
    unittest.main()
