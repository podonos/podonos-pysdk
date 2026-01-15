import unittest

from podonos.entity.verification import (
    FileVerificationResult,
    ProcessFilesResponse,
    VerificationErrorDetail,
    VerifyFilesResponse,
)


class TestVerificationErrorDetail(unittest.TestCase):
    def test_from_dict_with_all_fields(self):
        data = {
            "code": "FILE_MD5_MISMATCH",
            "message": "MD5 hash mismatch",
            "expected": "AA259hLYqLX6hjV81ve5Cg==",
            "actual": "rqXc34Ir5GRBYFV++6Traw==",
        }

        result = VerificationErrorDetail.from_dict(data)

        self.assertEqual(result.code, "FILE_MD5_MISMATCH")
        self.assertEqual(result.message, "MD5 hash mismatch")
        self.assertEqual(result.expected, "AA259hLYqLX6hjV81ve5Cg==")
        self.assertEqual(result.actual, "rqXc34Ir5GRBYFV++6Traw==")

    def test_from_dict_with_none(self):
        result = VerificationErrorDetail.from_dict(None)
        self.assertIsNone(result)

    def test_from_dict_with_minimal_fields(self):
        data = {"code": "FILE_NOT_FOUND_IN_S3", "message": "File not found"}

        result = VerificationErrorDetail.from_dict(data)

        self.assertEqual(result.code, "FILE_NOT_FOUND_IN_S3")
        self.assertEqual(result.message, "File not found")
        self.assertIsNone(result.expected)
        self.assertIsNone(result.actual)


class TestFileVerificationResult(unittest.TestCase):
    def test_from_dict_success(self):
        data = {
            "uploaded_file_name": "1234567890-uuid.wav",
            "verified": True,
            "file_meta_id": "e194e958-4a42-403e-8625-d4648e39b39c",
            "error": None,
        }

        result = FileVerificationResult.from_dict(data)

        self.assertEqual(result.uploaded_file_name, "1234567890-uuid.wav")
        self.assertTrue(result.verified)
        self.assertEqual(result.file_meta_id, "e194e958-4a42-403e-8625-d4648e39b39c")
        self.assertIsNone(result.error)

    def test_from_dict_failure(self):
        data = {
            "uploaded_file_name": "1234567890-uuid.wav",
            "verified": False,
            "file_meta_id": "e194e958-4a42-403e-8625-d4648e39b39c",
            "error": {
                "code": "FILE_MD5_MISMATCH",
                "message": "MD5 hash mismatch",
                "expected": "expected_md5",
                "actual": "actual_md5",
            },
        }

        result = FileVerificationResult.from_dict(data)

        self.assertEqual(result.uploaded_file_name, "1234567890-uuid.wav")
        self.assertFalse(result.verified)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, "FILE_MD5_MISMATCH")


class TestVerifyFilesResponse(unittest.TestCase):
    def test_from_dict_all_verified(self):
        data = {
            "all_verified": True,
            "verified_count": 2,
            "failed_count": 0,
            "results": [
                {
                    "uploaded_file_name": "file1.wav",
                    "verified": True,
                    "file_meta_id": "id1",
                    "error": None,
                },
                {
                    "uploaded_file_name": "file2.wav",
                    "verified": True,
                    "file_meta_id": "id2",
                    "error": None,
                },
            ],
        }

        result = VerifyFilesResponse.from_dict(data)

        self.assertTrue(result.all_verified)
        self.assertEqual(result.verified_count, 2)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(len(result.results), 2)

    def test_from_dict_partial_failure(self):
        data = {
            "all_verified": False,
            "verified_count": 1,
            "failed_count": 1,
            "results": [
                {
                    "uploaded_file_name": "file1.wav",
                    "verified": True,
                    "file_meta_id": "id1",
                    "error": None,
                },
                {
                    "uploaded_file_name": "file2.wav",
                    "verified": False,
                    "file_meta_id": "id2",
                    "error": {"code": "FILE_SIZE_MISMATCH", "message": "Size mismatch"},
                },
            ],
        }

        result = VerifyFilesResponse.from_dict(data)

        self.assertFalse(result.all_verified)
        self.assertEqual(result.verified_count, 1)
        self.assertEqual(result.failed_count, 1)
        failed_results = [r for r in result.results if not r.verified]
        self.assertEqual(len(failed_results), 1)
        self.assertEqual(failed_results[0].error.code, "FILE_SIZE_MISMATCH")


class TestProcessFilesResponse(unittest.TestCase):
    def test_from_dict(self):
        data = {
            "processing_count": 5,
            "file_meta_ids": ["id1", "id2", "id3", "id4", "id5"],
        }

        result = ProcessFilesResponse.from_dict(data)

        self.assertEqual(result.processing_count, 5)
        self.assertEqual(len(result.file_meta_ids), 5)
        self.assertIn("id1", result.file_meta_ids)


if __name__ == "__main__":
    unittest.main()
