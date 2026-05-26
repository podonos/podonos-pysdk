import os
import time
import unittest
from unittest.mock import MagicMock, patch

from podonos.common.enum import QuestionFileType
from podonos.core.file import Audio
from podonos.core.upload_manager import UploadManager
from podonos.errors import UploadBatchError
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

    def test_more_workers_than_files_does_not_hang(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=5)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        start = time.monotonic()
        self.assertTrue(upload_manager.wait_and_close())
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(upload_manager._total_uploaded, 1)  # type: ignore

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

    def test_upload_reuses_precomputed_integrity(self):
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
        audio.set_integrity_info("A" * 24, 123)

        with patch(
            "podonos.core.upload_manager.calculate_file_md5_base64",
            side_effect=AssertionError("integrity should be reused"),
        ) as mock_calculate:
            upload_manager.add_file_to_queue("EVALID", audio)
            self.assertTrue(upload_manager.wait_and_close())

        mock_calculate.assert_not_called()
        self.assertEqual(audio.content_md5, "A" * 24)
        self.assertEqual(audio.file_size, 123)

    def test_upload_failure_records_error_and_does_not_hang(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            side_effect=RuntimeError("S3 PUT failed")
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        start = time.monotonic()
        with self.assertRaises(UploadBatchError) as context:
            upload_manager.wait_and_close()
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5)
        self.assertNotIn(os.path.basename(TESTDATA_SPEECH_CH1_MP3), str(context.exception))
        self.assertNotIn(TESTDATA_SPEECH_CH1_MP3, str(context.exception))
        self.assertIn("REMOTE_1", str(context.exception))
        self.assertIn("S3 PUT failed", str(context.exception))
        self.assertEqual(upload_manager._total_uploaded, 0)  # type: ignore
        self.assertFalse(upload_manager.wait_and_close())

    def test_upload_failure_redacts_presigned_url_secrets(self):
        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(evaluation_service=eval_service, max_workers=1)
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            side_effect=RuntimeError(
                "PUT failed for https://bucket.s3.amazonaws.com/file.wav"
                "?X-Amz-Signature=SECRET&X-Amz-Credential=CREDENTIAL "
                "Authorization: Bearer TOKEN"
            )
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        with self.assertRaises(UploadBatchError) as context:
            upload_manager.wait_and_close()

        message = str(context.exception)
        self.assertNotIn("SECRET", message)
        self.assertNotIn("CREDENTIAL", message)
        self.assertNotIn("TOKEN", message)
        self.assertIn("[REDACTED]", message)

    def test_ledger_failure_warning_is_redacted(self):
        eval_service = EvaluationService(api_client=MagicMock())
        ledger = MagicMock()
        ledger.mark_upload_failed.side_effect = RuntimeError("X-API-KEY=SECRET")
        upload_manager = UploadManager(
            evaluation_service=eval_service,
            max_workers=1,
            upload_ledger=ledger,
        )
        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_LEDGER_ERROR")

        with patch("podonos.core.upload_manager.log.warning") as mock_warning:
            upload_manager._record_upload_error(  # type: ignore[attr-defined]
                "EVALID", audio, RuntimeError("upload failed")
            )

        log_message = mock_warning.call_args.args[0]
        self.assertNotIn("SECRET", log_message)
        self.assertIn("[REDACTED]", log_message)
        with self.assertRaises(UploadBatchError):
            upload_manager.wait_and_close()

    def test_ledger_md5_failure_fails_upload_before_presigned_url(self):
        eval_service = EvaluationService(api_client=MagicMock())
        ledger = MagicMock()
        ledger.mark_md5_ready.side_effect = RuntimeError(
            "sqlite write failed X-API-KEY=SECRET"
        )
        upload_manager = UploadManager(
            evaluation_service=eval_service,
            max_workers=1,
            upload_ledger=ledger,
        )
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock()  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_LEDGER_MD5")
        upload_manager.add_file_to_queue("EVALID", audio)

        with self.assertRaises(UploadBatchError) as context:
            upload_manager.wait_and_close()

        message = str(context.exception)
        self.assertIn("Failed to update upload ledger md5_ready", message)
        self.assertNotIn("SECRET", message)
        upload_manager._evaluation_service.get_presigned_url.assert_not_called()  # type: ignore[attr-defined]
        upload_manager._evaluation_service.upload_evaluation_file.assert_not_called()  # type: ignore[attr-defined]
        ledger.mark_upload_failed.assert_called_once()
        self.assertEqual(upload_manager._total_uploaded, 0)  # type: ignore

    def test_ledger_uploaded_failure_fails_upload_after_put(self):
        eval_service = EvaluationService(api_client=MagicMock())
        ledger = MagicMock()
        ledger.mark_uploaded.side_effect = RuntimeError(
            "sqlite write failed X-Amz-Signature=SECRET"
        )
        upload_manager = UploadManager(
            evaluation_service=eval_service,
            max_workers=1,
            upload_ledger=ledger,
        )
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=MagicMock()
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_LEDGER_UPLOADED")
        upload_manager.add_file_to_queue("EVALID", audio)

        with self.assertRaises(UploadBatchError) as context:
            upload_manager.wait_and_close()

        message = str(context.exception)
        self.assertIn("Failed to update upload ledger uploaded", message)
        self.assertNotIn("SECRET", message)
        upload_manager._evaluation_service.upload_evaluation_file.assert_called_once()  # type: ignore[attr-defined]
        ledger.mark_upload_failed.assert_called_once()
        self.assertEqual(upload_manager._total_uploaded, 0)  # type: ignore

    def test_upload_manager_passes_upload_timeout(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = None

        eval_service = EvaluationService(api_client=MagicMock())
        upload_manager = UploadManager(
            evaluation_service=eval_service,
            max_workers=1,
            api_timeout=(3, 33),
            upload_timeout=(11, 222),
        )
        upload_manager._evaluation_service.get_presigned_url = MagicMock(
            return_value="https://example.com/presigned-url"
        )  # type: ignore
        upload_manager._evaluation_service.upload_evaluation_file = MagicMock(
            return_value=mock_response
        )  # type: ignore

        audio = create_test_audio(TESTDATA_SPEECH_CH1_MP3, "REMOTE_1")
        upload_manager.add_file_to_queue("EVALID", audio)

        self.assertTrue(upload_manager.wait_and_close())
        upload_manager._evaluation_service.upload_evaluation_file.assert_called_once()  # type: ignore
        upload_manager._evaluation_service.get_presigned_url.assert_called_once()  # type: ignore
        _, presigned_kwargs = upload_manager._evaluation_service.get_presigned_url.call_args  # type: ignore
        self.assertEqual(presigned_kwargs["timeout"], (3, 33))
        _, kwargs = upload_manager._evaluation_service.upload_evaluation_file.call_args  # type: ignore
        self.assertEqual(kwargs["timeout"], (11, 222))
        self.assertEqual(kwargs["context"]["evaluation_id"], "EVALID")


if __name__ == "__main__":
    unittest.main()
