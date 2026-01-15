import os
import unittest

from datetime import datetime
from unittest.mock import MagicMock

from podonos.common.enum import QuestionFileType
from podonos.core.file import Audio
from podonos.core.upload_manager import UploadManager
from podonos.service.evaluation_service import EvaluationService

TESTDATA_SPEECH_CH1_MP3 = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
TESTDATA_SPEECH_TWO_CH1_WAV = os.path.join(
    os.path.dirname(__file__), "speech_two_ch1.wav"
)


def create_test_audio(path: str, remote_name: str) -> Audio:
    return Audio(
        path=path,
        name=os.path.basename(path),
        remote_object_name=remote_name,
        script=None,
        tags=[],
        model_tag="test_model",
        is_ref=False,
        group=None,
        type=QuestionFileType.STIMULUS,
        order_in_group=0,
    )


class TestUploadManager(unittest.TestCase):
    def test_upload_manager_with_audio_object(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        self.assertTrue(upload_manager.wait_and_close())

    def test_wait_and_close_without_files(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        self.assertTrue(upload_manager.wait_and_close())

    def test_get_upload_time_after_uploads(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        self.assertTrue(upload_manager.wait_and_close())

        start, finish = upload_manager.get_upload_time()
        self.assertIn("REMOTE_1", start)
        self.assertIn("REMOTE_1", finish)

    def test_add_file_to_queue_when_uninitialized_raises(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._queue = None  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")

        try:
            with self.assertRaises(ValueError):
                upload_manager.add_file_to_queue("EVALID", audio)
        finally:
            upload_manager._status = False  # type: ignore

    def test_multiple_file_uploads_updates_counters(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=2)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio_a = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_A")
        audio_b = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_B")

        upload_manager.add_file_to_queue("EVALID", audio_a)
        upload_manager.add_file_to_queue("EVALID", audio_b)

        self.assertTrue(upload_manager.wait_and_close())
        self.assertEqual(upload_manager._total_uploaded, 2)  # type: ignore

    def test_md5_calculated_during_upload(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_TWO_CH1_WAV, "REMOTE_1")

        self.assertIsNone(audio.content_md5)
        self.assertIsNone(audio.file_size)

        upload_manager.add_file_to_queue("EVALID", audio)
        self.assertTrue(upload_manager.wait_and_close())

        self.assertIsNotNone(audio.content_md5)
        self.assertIsNotNone(audio.file_size)
        self.assertEqual(len(audio.content_md5), 24)
        self.assertGreater(audio.file_size, 0)


if __name__ == "__main__":
    unittest.main()
