import unittest

from datetime import datetime
from unittest.mock import MagicMock

from podonos.core.upload_manager import UploadManager
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

        upload_manager = UploadManager(evaluation_service=MagicMock(), max_workers=1)
        upload_manager._evaluation_service.get_presigned_url.return_value = "https://example.com/presigned-url"
        upload_manager._evaluation_service.upload_evaluation_file.return_value = mock_response

        evaluation_id = "AAAA1234"
        remote_object_name = "ABCD1234"
        path = TESTDATA_SPEECH_CH1_MP3
        upload_manager.add_file_to_queue(evaluation_id, remote_object_name, path)

        self.assertTrue(upload_manager.wait_and_close())


if __name__ == "__main__":
    unittest.main()
