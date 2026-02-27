import unittest

from podonos.entity.flash_eval import FlashEvalResult, FlashFileInfo


class TestFlashFileInfo(unittest.TestCase):
    def test_from_dict(self):
        data = {"filename": "test.wav", "filetype": "TARGET_1", "mimetype": "audio/wav"}
        info = FlashFileInfo.from_dict(data)
        self.assertEqual(info.filename, "test.wav")
        self.assertEqual(info.filetype, "TARGET_1")
        self.assertEqual(info.mimetype, "audio/wav")

    def test_from_dict_missing_fields(self):
        info = FlashFileInfo.from_dict({})
        self.assertEqual(info.filename, "")
        self.assertEqual(info.filetype, "")
        self.assertEqual(info.mimetype, "")


class TestFlashEvalResult(unittest.TestCase):
    def test_from_dict_with_scores(self):
        data = {
            "scores": {"naturalness": 3.6},
            "files": [
                {"filename": "audio.wav", "filetype": "TARGET_1", "mimetype": "audio/wav"}
            ],
            "message": "success",
        }
        result = FlashEvalResult.from_dict(data)
        self.assertEqual(result.naturalness, 3.6)
        self.assertEqual(len(result.files), 1)
        self.assertEqual(result.files[0].filename, "audio.wav")
        self.assertEqual(result.message, "success")

    def test_from_dict_without_scores(self):
        data = {"files": [], "message": None}
        result = FlashEvalResult.from_dict(data)
        self.assertIsNone(result.naturalness)
        self.assertEqual(len(result.files), 0)
        self.assertIsNone(result.message)

    def test_from_dict_empty(self):
        result = FlashEvalResult.from_dict({})
        self.assertIsNone(result.naturalness)
        self.assertEqual(result.files, [])
        self.assertIsNone(result.message)

    def test_from_dict_scores_not_dict(self):
        data = {"scores": "invalid", "files": []}
        result = FlashEvalResult.from_dict(data)
        self.assertIsNone(result.naturalness)

    def test_from_dict_multiple_files(self):
        data = {
            "scores": {"naturalness": 4.2},
            "files": [
                {"filename": "a.wav", "filetype": "TARGET_1", "mimetype": "audio/wav"},
                {"filename": "b.mp3", "filetype": "TARGET_1", "mimetype": "audio/mpeg"},
            ],
        }
        result = FlashEvalResult.from_dict(data)
        self.assertEqual(result.naturalness, 4.2)
        self.assertEqual(len(result.files), 2)
        self.assertEqual(result.files[1].filename, "b.mp3")


if __name__ == "__main__":
    unittest.main()
