import os
import unittest
from unittest.mock import patch

from podonos.core.file import File


class TestFile(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_should_create_file_successfully(self):
        # Given
        model_tag = "test_model"
        tags = ["test", "mono"]
        script = "test script"

        # When
        file = File(path=self.test_wav, model_tag=model_tag, tags=tags, script=script, is_ref=False)

        # Then
        self.assertEqual(file.path, self.test_wav)
        self.assertEqual(file.model_tag, model_tag)
        self.assertEqual(file.tags, tags)
        self.assertEqual(file.script, script)
        self.assertFalse(file.is_ref)

    def test_should_create_file_with_minimal_params(self):
        # Given
        model_tag = "test_model"

        # When
        file = File(path=self.test_wav, model_tag=model_tag)

        # Then
        self.assertEqual(file.path, self.test_wav)
        self.assertEqual(file.model_tag, model_tag)
        self.assertEqual(file.tags, [])
        self.assertIsNone(file.script)
        self.assertFalse(file.is_ref)

    def test_should_deduplicate_tags(self):
        # Given
        tags = ["test", "mono", "test", "mono", "unique"]

        # When
        file = File(path=self.test_wav, model_tag="test_model", tags=tags)

        # Then
        self.assertEqual(file.tags, ["test", "mono", "unique"])

    def test_should_raise_error_for_nonexistent_file(self):
        # Given
        nonexistent_path = "nonexistent.wav"

        # When/Then
        with self.assertRaises(FileNotFoundError) as context:
            File(path=nonexistent_path, model_tag="test_model")
        self.assertIn("doesn't exist", str(context.exception))

    def test_should_raise_error_for_unreadable_file(self):
        # Given
        with patch("os.access", return_value=False):
            # When/Then
            with self.assertRaises(FileNotFoundError) as context:
                File(path=self.test_wav, model_tag="test_model")
            self.assertIn("isn't readable", str(context.exception))

    def test_should_validate_path_successfully(self):
        # Given
        file = File(path=self.test_wav, model_tag="test_model")

        # When
        validated_path = file._validate_path(self.test_wav)

        # Then
        self.assertEqual(validated_path, self.test_wav)

    def test_should_set_tags_successfully(self):
        # Given
        tags = ["test", "mono", "test", "unique"]
        file = File(path=self.test_wav, model_tag="test_model")

        # When
        unique_tags = file._set_tags(tags)

        # Then
        self.assertEqual(unique_tags, ["test", "mono", "unique"])
        self.assertEqual(len(unique_tags), len(set(unique_tags)))  # 중복 확인


if __name__ == "__main__":
    unittest.main()
