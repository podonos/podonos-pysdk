import os
import unittest
from unittest.mock import patch


from podonos.core.config import EvalConfig
from podonos.core.file import File, FileValidator, FileTransformer, AudioGroup
from podonos.common.enum import QuestionFileType


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
        self.assertEqual(len(unique_tags), len(set(unique_tags)))

    def test_file_validator_should_validate_single_stimulus_successfully(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="NMOS", num_eval=1)
        file_validator = FileValidator(eval_config)
        file = File(path=self.test_wav, model_tag="test_model")

        # When/Then
        file_validator.validate_file(file)

    def test_file_validator_should_validate_files_preference_successfully(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        file_validator.validate_files([file0, file1])  # Should not raise

    @unittest.skip("Skip this test because CMOS type is not supported yet")
    def test_file_validator_should_validate_files_cmos_type(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="CMOS", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2", is_ref=True)

        # When/Then
        file_validator.validate_files([file0, file1])  # Should not raise

    def test_file_validator_should_validate_files_csmos_type(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="CSMOS", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")
        file2 = File(path=self.test_wav, model_tag="model3", is_ref=True)

        # When/Then
        file_validator.validate_files([file0, file1, file2])  # Should not raise

    def test_file_validator_should_validate_files_preference_raise_error(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_files([file0, file1])

    @unittest.skip("Skip this test because CMOS type is not supported yet")
    def test_file_validator_raise_error_in_cmos_type(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="CMOS", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2", is_ref=True)

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_files([file0, file1])

    def test_file_validator_raise_error_when_annotation_is_true_and_script_is_none(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="NMOS", num_eval=1, use_annotation=True)
        file_validator = FileValidator(eval_config)
        file = File(path=self.test_wav, model_tag="model1", script=None)

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_file(file)

    def test_file_transformer_should_transform_file_to_audio_single_stimulus(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="NMOS", num_eval=1, use_annotation=True)
        file = File(path=self.test_wav, model_tag="test_model", script="test script")
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)
        self.assertEqual(audio_group.audios[0].path, file.path)
        self.assertEqual(audio_group.audios[0].group, None)
        self.assertEqual(audio_group.audios[0].type, QuestionFileType.STIMULUS)

    def test_file_transformer_should_transform_file_to_audio_double_stimulus(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file0 = File(path=self.test_wav, model_tag="test_model")
        file1 = File(path=self.test_wav, model_tag="test_model")
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file0, file1])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)
        self.assertEqual(audio_group.audios[0].path, file0.path)
        self.assertEqual(audio_group.audios[1].path, file1.path)

    def test_file_transformer_should_transform_file_to_audio_double_stimulus_with_ref(self):
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="CSMOS", num_eval=1)
        file0 = File(path=self.test_wav, model_tag="test_model")
        file1 = File(path=self.test_wav, model_tag="test_model", is_ref=True)
        file2 = File(path=self.test_wav, model_tag="test_model")
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file0, file1, file2])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)


if __name__ == "__main__":
    unittest.main()
