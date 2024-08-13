import os
import unittest
import requests

from datetime import datetime
from typing import Optional
from unittest import mock
from unittest.mock import Mock, patch, MagicMock

from podonos.common.enum import QuestionFileType
from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluation import Evaluation
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from podonos.core.upload_manager import UploadManager
from tests.test_audio import TESTDATA_SPEECH_CH1_MP3


class TestUploadManager(unittest.TestCase):

    def setUp(self):
        print('aa')

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

        upload_manager = UploadManager(api_client=MagicMock(), max_workers=1)
        upload_manager._api_client.post.return_value = mock_response  # type: ignore

        presigned_url = "https://fake.podonos.com/upload"
        remote_object_name = "ABCD1234"
        path = TESTDATA_SPEECH_CH1_MP3
        upload_manager.add_file_to_queue(presigned_url, remote_object_name, path)

        self.assertTrue(upload_manager.wait_and_close())


if __name__ == '__main__':
    unittest.main()
