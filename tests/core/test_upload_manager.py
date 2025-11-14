import unittest

from datetime import datetime
from unittest.mock import MagicMock

from podonos.core.upload_manager import UploadManager
from podonos.service.evaluation_service import EvaluationService
from tests.core.test_audio import TESTDATA_SPEECH_CH1_MP3


class TestUploadManager(unittest.TestCase):
    def test_upload_manager(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None  # No exception
        mock_response.json.return_value = {
            "id": "123",
            "title": "title",
            "internal_name": None,
            "description": None,
            "status": "DRAFT",
            "created_time": datetime.now().isoformat(),
            "updated_time": datetime.now().isoformat(),
        }

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        # Patch instance methods to avoid real network calls
        upload_manager._evaluation_service.get_presigned_url = MagicMock(return_value="https://example.com/presigned-url")  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(return_value=mock_response)  # type: ignore

        evaluation_id = "AAAA1234"
        remote_object_name = "ABCD1234"
        path = TESTDATA_SPEECH_CH1_MP3
        upload_manager.add_file_to_queue(evaluation_id, remote_object_name, path)

        self.assertTrue(upload_manager.wait_and_close())

    def test_wait_and_close_without_files(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        # No files added; should still close cleanly
        self.assertTrue(upload_manager.wait_and_close())

    def test_get_upload_time_after_uploads(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(return_value="https://example.com/presigned-url")  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(return_value=mock_response)  # type: ignore

        upload_manager.add_file_to_queue("EVALID", "REMOTE_1", TESTDATA_SPEECH_CH1_MP3)
        self.assertTrue(upload_manager.wait_and_close())
        start, finish = upload_manager.get_upload_time()
        self.assertIn("REMOTE_1", start)
        self.assertIn("REMOTE_1", finish)

    def test_add_file_to_queue_when_uninitialized_raises(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        # Force uninitialized state for queue to trigger validation error
        upload_manager._queue = None  # type: ignore
        try:
            with self.assertRaises(ValueError):
                upload_manager.add_file_to_queue("EVALID", "REMOTE_1", TESTDATA_SPEECH_CH1_MP3)
        finally:
            # Prevent atexit callback from raising after this test
            upload_manager._status = False  # type: ignore

    def test_multiple_file_uploads_updates_counters(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=2)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(return_value="https://example.com/presigned-url")  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(return_value=mock_response)  # type: ignore

        upload_manager.add_file_to_queue("EVALID", "REMOTE_A", TESTDATA_SPEECH_CH1_MP3)
        upload_manager.add_file_to_queue("EVALID", "REMOTE_B", TESTDATA_SPEECH_CH1_MP3)
        self.assertTrue(upload_manager.wait_and_close())
        # _total_uploaded should be 2 after processing two files
        self.assertEqual(upload_manager._total_uploaded, 2)  # type: ignore


if __name__ == "__main__":
    unittest.main()
