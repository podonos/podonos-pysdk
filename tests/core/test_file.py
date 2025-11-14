import os
import unittest
from unittest.mock import patch, MagicMock
from typing import Any
from glog import FailedCheckException  # type: ignore

from podonos.core.config import EvalConfig
from podonos.core.file import File, FileValidator, FileTransformer, AudioGroup, AudioMeta
from podonos.common.enum import QuestionFileType


class TestFile(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    # ----------------------------
    # meta_data validation tests
    # ----------------------------
    def test_validate_meta_data_should_allow_none(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When
        result = f._validate_meta_data(None)  # type: ignore
        # Then
        self.assertIsNone(result)

    def test_validate_meta_data_should_allow_empty_dict(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When
        result = f._validate_meta_data({})  # type: ignore
        # Then
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_validate_meta_data_should_allow_primitive_value_types(self):
        # Given
        valid_meta = {
            "str_key": "value",
            "int_key": 123,
            "float_key": 1.23,
            "bool_true": True,
            "bool_false": False,
            "none_key": None,
        }
        f = File(path=self.test_wav, model_tag="test_model")
        # When
        result = f._validate_meta_data(valid_meta)  # type: ignore
        # Then
        self.assertEqual(result, valid_meta)

    def test_validate_meta_data_should_reject_non_dict_input(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(FailedCheckException):
            f._validate_meta_data(["not", "a", "dict"])  # type: ignore

    def test_validate_meta_data_should_reject_non_string_keys(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(ValueError) as ctx:
            f._validate_meta_data({1: "value"})  # type: ignore
        self.assertIn("meta_data key must be a string", str(ctx.exception))

    def test_validate_meta_data_should_reject_list_value(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(ValueError) as ctx:
            f._validate_meta_data({"k": [1, 2, 3]})  # type: ignore
        self.assertIn("non-iterable JSON-primitive", str(ctx.exception))

    def test_validate_meta_data_should_reject_tuple_value(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(ValueError) as ctx:
            f._validate_meta_data({"k": (1, 2)})  # type: ignore
        self.assertIn("non-iterable JSON-primitive", str(ctx.exception))

    def test_validate_meta_data_should_reject_set_value(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(ValueError) as ctx:
            f._validate_meta_data({"k": {1, 2, 3}})  # type: ignore
        self.assertIn("non-iterable JSON-primitive", str(ctx.exception))

    def test_validate_meta_data_should_reject_dict_value(self):
        # Given
        f = File(path=self.test_wav, model_tag="test_model")
        # When/Then
        with self.assertRaises(ValueError) as ctx:
            f._validate_meta_data({"k": {"nested": "v"}})  # type: ignore
        self.assertIn("non-iterable JSON-primitive", str(ctx.exception))

    def test_validate_meta_data_should_preserve_values(self):
        # Given
        meta = {"a": "x", "b": 2, "c": 3.14, "d": False, "e": None}
        f = File(path=self.test_wav, model_tag="test_model")
        # When
        result = f._validate_meta_data(meta)  # type: ignore
        # Then
        self.assertEqual(result, meta)

    def test_validate_meta_data_large_payload(self):
        # Given
        big_meta = {f"k{i}": i for i in range(100)}
        f = File(path=self.test_wav, model_tag="test_model")
        # When
        result = f._validate_meta_data(big_meta)  # type: ignore
        # Then
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result.keys()), 100)  # type: ignore
        self.assertEqual(result["k0"], 0)  # type: ignore
        self.assertEqual(result["k99"], 99)  # type: ignore

    def test_file_constructor_should_accept_valid_meta_data(self):
        # Given
        meta = {"speaker_id": "spk1", "age": 30, "premium": True, "score": 9.5, "note": None}
        # When
        f = File(path=self.test_wav, model_tag="test_model", meta_data=meta)
        # Then
        self.assertEqual(f.meta_data, meta)

    def test_file_constructor_should_reject_invalid_meta_data(self):
        # Given
        invalid_meta = {"arr": [1, 2, 3]}
        # When/Then
        with self.assertRaises(ValueError):
            File(path=self.test_wav, model_tag="test_model", meta_data=invalid_meta)

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

    def test_should_raise_error_for_model_tag_with_invalid_characters(self):
        """Test that File raises error when model_tag contains invalid characters"""
        # Test various invalid characters
        invalid_chars = [
            "@",
            "!",
            "#",
            "$",
            "%",
            "^",
            "&",
            "*",
            "(",
            ")",
            "+",
            "=",
            "[",
            "]",
            "{",
            "}",
            "|",
            "\\",
            ":",
            ";",
            '"',
            "'",
            "<",
            ">",
            ",",
            ".",
            "?",
            "/",
            "~",
            "`",
        ]

        for char in invalid_chars:
            with self.subTest(char=char):
                with self.assertRaises(ValueError) as context:
                    File(path=self.test_wav, model_tag=f"test{char}model")
                self.assertIn("contains invalid characters", str(context.exception))
                self.assertIn(char, str(context.exception))

    def test_should_accept_model_tag_with_hyphen_and_underscore(self):
        """Test that File accepts model_tag with hyphens and underscores"""
        # These should work without raising errors
        valid_tags = ["test-model", "test_model", "test-model_123", "TEST-MODEL_123"]

        for tag in valid_tags:
            with self.subTest(tag=tag):
                file = File(path=self.test_wav, model_tag=tag)
                self.assertEqual(file.model_tag, tag)

    def test_should_accept_model_tag_with_alphanumeric_only(self):
        """Test that File accepts model_tag with alphanumeric characters only"""
        # These should work without raising errors
        valid_tags = ["testmodel", "TestModel", "test123", "123test", "TEST123"]

        for tag in valid_tags:
            with self.subTest(tag=tag):
                file = File(path=self.test_wav, model_tag=tag)
                self.assertEqual(file.model_tag, tag)

    def test_should_accept_model_tag_with_unicode_letters(self):
        """Test that File accepts model_tag with Unicode letters from various languages"""
        # These should work without raising errors
        valid_tags = [
            "모델A",  # Korean
            "モデルB",  # Japanese
            "模型C",  # Chinese
            "модельD",  # Russian
            "modèleE",  # French with accent
            "modeloF",  # Spanish
            "test-모델_123",  # Mixed Korean with hyphens and underscores
            "TEST-モデル_456",  # Mixed Japanese with hyphens and underscores
            "Test-模型_789",  # Mixed Chinese with hyphens and underscores
        ]

        for tag in valid_tags:
            with self.subTest(tag=tag):
                file = File(path=self.test_wav, model_tag=tag)
                self.assertEqual(file.model_tag, tag)

    def test_should_raise_error_for_model_tag_with_spaces(self):
        """Test that File raises error when model_tag contains spaces"""
        with self.assertRaises(ValueError) as context:
            File(path=self.test_wav, model_tag="test model")
        self.assertIn("contains invalid characters", str(context.exception))
        self.assertIn(" ", str(context.exception))

    def test_should_validate_path_successfully(self):
        # Given
        file = File(path=self.test_wav, model_tag="test_model")

        # When
        validated_path = file._validate_path(self.test_wav)  # type: ignore

        # Then
        self.assertEqual(validated_path, self.test_wav)

    def test_should_set_tags_successfully(self):
        # Given
        tags = ["test", "mono", "test", "unique"]
        file = File(path=self.test_wav, model_tag="test_model")

        # When
        unique_tags = file._set_tags(tags)  # type: ignore

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
        file0 = File(path=self.test_wav, model_tag="test_model", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="test_model", meta_data={"key": "value"})
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
        file0 = File(path=self.test_wav, model_tag="test_model", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="test_model", is_ref=True)
        file2 = File(path=self.test_wav, model_tag="test_model", meta_data={"key": "value"})
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file0, file1, file2])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)

    def test_validate_double_stimuli_model_tags_should_raise_error_for_same_model_tags(self):
        """Test that _validate_double_stimuli_model_tags raises error when model tags are identical"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="same_model", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="same_model", meta_data={"key": "value"})

        # When/Then
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_raise_error_for_case_insensitive_same_model_tags(self):
        """Test that _validate_double_stimuli_model_tags raises error when model tags are same but different case"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="ModelA", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="modela", meta_data={"key": "value"})

        # When/Then
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_allow_first_pair(self):
        """Test that _validate_double_stimuli_model_tags allows the first occurrence of a pair"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="google", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="openai", meta_data={"key": "value"})

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].model_tag, "google")
        self.assertEqual(result[1].model_tag, "openai")

    def test_validate_double_stimuli_model_tags_should_allow_consistent_pair_order(self):
        """Test that _validate_double_stimuli_model_tags allows consistent pair ordering"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai
        file0 = File(path=self.test_wav, model_tag="google", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="openai", meta_data={"key": "value"})
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: same order google -> openai
        file2 = File(path=self.test_wav, model_tag="google")
        file3 = File(path=self.test_wav, model_tag="openai")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)
        self.assertEqual(result1[0].model_tag, "google")
        self.assertEqual(result1[1].model_tag, "openai")
        self.assertEqual(result2[0].model_tag, "google")
        self.assertEqual(result2[1].model_tag, "openai")

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_raise_error_for_inconsistent_pair_order(self):
        """Test that _validate_double_stimuli_model_tags raises error for inconsistent pair ordering"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: reversed order openai -> google (should raise error)
        file2 = File(path=self.test_wav, model_tag="openai")
        file3 = File(path=self.test_wav, model_tag="google")

        # When/Then
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore
        self.assertIn("Inconsistent model tag pair order", str(context.exception))

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_allow_different_pairs(self):
        """Test that _validate_double_stimuli_model_tags allows different model pairs"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: elevenlabs -> openai (different pair)
        file2 = File(path=self.test_wav, model_tag="elevenlabs")
        file3 = File(path=self.test_wav, model_tag="openai")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)
        self.assertEqual(result1[0].model_tag, "google")
        self.assertEqual(result1[1].model_tag, "openai")
        self.assertEqual(result2[0].model_tag, "elevenlabs")
        self.assertEqual(result2[1].model_tag, "openai")

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_handle_case_insensitive_pairs(self):
        """Test that _validate_double_stimuli_model_tags handles case insensitive pair comparison"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: Google -> OpenAI
        file0 = File(path=self.test_wav, model_tag="Google")
        file1 = File(path=self.test_wav, model_tag="OpenAI")
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: google -> openai (same pair, different case)
        file2 = File(path=self.test_wav, model_tag="google")
        file3 = File(path=self.test_wav, model_tag="openai")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)

    def test_validate_double_stimuli_model_tags_should_preserve_original_case(self):
        """Test that _validate_double_stimuli_model_tags preserves original case in returned files"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="Google")
        file1 = File(path=self.test_wav, model_tag="OpenAI")

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)
        # Original case should be preserved
        self.assertEqual(result[0].model_tag, "Google")
        self.assertEqual(result[1].model_tag, "OpenAI")

    def test_validate_double_stimuli_model_tags_should_preserve_file_properties(self):
        """Test that _validate_double_stimuli_model_tags preserves all file properties"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="ModelB", tags=["tag1", "tag2"], script="script1", is_ref=False)
        file1 = File(path=self.test_wav, model_tag="ModelA", tags=["tag3"], script="script2", is_ref=True)

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)

        # Check properties are preserved
        self.assertEqual(result[0].model_tag, "ModelB")
        self.assertEqual(result[0].tags, ["tag1", "tag2"])
        self.assertEqual(result[0].script, "script1")
        self.assertFalse(result[0].is_ref)

        self.assertEqual(result[1].model_tag, "ModelA")
        self.assertEqual(result[1].tags, ["tag3"])
        self.assertEqual(result[1].script, "script2")
        self.assertTrue(result[1].is_ref)

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_handle_leading_trailing_spaces(self):
        """Test that _validate_double_stimuli_model_tags works with leading/trailing spaces"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        file0 = File(path=self.test_wav, model_tag=" ModelA ")
        file1 = File(path=self.test_wav, model_tag="modela")

        # When/Then
        with self.assertRaises(ValueError):
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

    def test_validate_double_stimuli_model_tags_should_handle_numeric_string_tags(self):
        """Test that _validate_double_stimuli_model_tags works with numeric string model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="100")
        file1 = File(path=self.test_wav, model_tag="2")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        # New logic preserves original order, not sorted
        self.assertEqual([f.model_tag for f in result], ["100", "2"])

    def test_validate_double_stimuli_model_tags_should_handle_special_symbols(self):
        """Test that _validate_double_stimuli_model_tags works with special symbols in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="AAA")
        file1 = File(path=self.test_wav, model_tag="BBB")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["AAA", "BBB"])

    def test_validate_double_stimuli_model_tags_should_handle_long_strings(self):
        """Test that _validate_double_stimuli_model_tags works with long strings in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="A" * 100)
        file1 = File(path=self.test_wav, model_tag="B" * 100)
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["A" * 100, "B" * 100])

    def test_validate_double_stimuli_model_tags_should_handle_unicode_emoji(self):
        """Test that _validate_double_stimuli_model_tags works with unicode letters in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="모델A")
        file1 = File(path=self.test_wav, model_tag="모델B")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["모델A", "모델B"])

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_handle_mixed_case_and_symbols(self):
        """Test that _validate_double_stimuli_model_tags works with mixed case and valid symbols in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="Model-A")
        file1 = File(path=self.test_wav, model_tag="model-a")
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_allow_exactly_two_model_tags(self):
        """Test that _validate_double_stimuli_model_tags allows exactly 2 model tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai (should work)
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: same model tags (should work)
        file2 = File(path=self.test_wav, model_tag="google")
        file3 = File(path=self.test_wav, model_tag="openai")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)
        self.assertEqual(result1[0].model_tag, "google")
        self.assertEqual(result1[1].model_tag, "openai")
        self.assertEqual(result2[0].model_tag, "google")
        self.assertEqual(result2[1].model_tag, "openai")

    def test_validate_double_stimuli_model_tags_should_reject_third_model_tag(self):
        """Test that _validate_double_stimuli_model_tags rejects a third model tag"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai (should work)
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: google -> elevenlabs (should fail - elevenlabs is not in allowed set)
        file2 = File(path=self.test_wav, model_tag="google")
        file3 = File(path=self.test_wav, model_tag="elevenlabs")

        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore
        self.assertIn("The number of model tags should be 2", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_reject_third_model_tag_reverse(self):
        """Test that _validate_double_stimuli_model_tags rejects a third model tag in reverse order"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai (should work)
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: elevenlabs -> google (should fail - elevenlabs is not in allowed set)
        file2 = File(path=self.test_wav, model_tag="elevenlabs")
        file3 = File(path=self.test_wav, model_tag="google")

        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore
        self.assertIn("The number of model tags should be 2", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_allow_reverse_order_of_same_pair(self):
        """Test that _validate_double_stimuli_model_tags allows reverse order of the same pair"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai (should work)
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: openai -> google (should work - same pair, reverse order)
        file2 = File(path=self.test_wav, model_tag="openai")
        file3 = File(path=self.test_wav, model_tag="google")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)
        self.assertEqual(result1[0].model_tag, "google")
        self.assertEqual(result1[1].model_tag, "openai")
        self.assertEqual(result2[0].model_tag, "openai")
        self.assertEqual(result2[1].model_tag, "google")

    def test_validate_double_stimuli_model_tags_should_reject_third_model_tag_case_insensitive(self):
        """Test that _validate_double_stimuli_model_tags rejects third model tag with case insensitive validation"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)

        # First pair: Google -> OpenAI (should work)
        file0 = File(path=self.test_wav, model_tag="Google")
        file1 = File(path=self.test_wav, model_tag="OpenAI")
        file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: google -> ELEVENLABS (should fail - ELEVENLABS is not in allowed set)
        file2 = File(path=self.test_wav, model_tag="google")
        file3 = File(path=self.test_wav, model_tag="ELEVENLABS")

        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore
        self.assertIn("The number of model tags should be 2", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_handle_non_latin_scripts(self):
        """Test that _validate_double_stimuli_model_tags works with non-latin scripts in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="가나다")
        file1 = File(path=self.test_wav, model_tag="나다라")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["가나다", "나다라"])

    def test_validate_double_stimuli_model_tags_should_handle_identical_unicode_different_normalization(self):
        """Test that _validate_double_stimuli_model_tags works with different unicode normalization in model_tags"""
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        tag1 = "é"  # NFC (default)
        tag2 = "é"  # Same character, different normalization might not matter for our validation

        file0 = File(path=self.test_wav, model_tag=tag1)
        file1 = File(path=self.test_wav, model_tag=tag2)

        # When/Then
        # These should be considered the same and raise an error
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_handle_model_tags_with_newlines(self):
        """Test that _validate_double_stimuli_model_tags works with newlines in model_tags"""
        # Given
        eval_config = EvalConfig(name="test_name", desc="test_desc", type="PREF", num_eval=1)
        file_validator = FileValidator(eval_config)
        # Note: File constructor strips whitespace, so newlines are removed
        file0 = File(path=self.test_wav, model_tag="ModelA\n")
        file1 = File(path=self.test_wav, model_tag="ModelB")

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)
        # File constructor strips whitespace, so "ModelA\n" becomes "ModelA"
        model_tags = [f.model_tag for f in result]
        self.assertIn("ModelA", model_tags)
        self.assertIn("ModelB", model_tags)


class TestAudioMeta(unittest.TestCase):
    """Test cases for AudioMeta class and format detection functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_detect_audio_format_wav(self):
        """Test _detect_audio_format correctly identifies WAV files"""
        audio_meta = AudioMeta(self.test_wav)
        detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
        self.assertEqual(detected_format, "wav")

    @patch("filetype.guess")
    def test_detect_audio_format_mp3(self, mock_guess: Any):
        """Test _detect_audio_format correctly identifies MP3 files"""
        # Mock filetype to return MP3 MIME type
        mock_kind = MagicMock()
        mock_kind.mime = "audio/mpeg"
        mock_kind.extension = "mp3"
        mock_guess.return_value = mock_kind

        audio_meta = AudioMeta(self.test_wav)
        detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
        self.assertEqual(detected_format, "mp3")

    @patch("filetype.guess")
    def test_detect_audio_format_flac(self, mock_guess: Any):
        """Test _detect_audio_format correctly identifies FLAC files"""
        # Mock filetype to return FLAC MIME type
        mock_kind = MagicMock()
        mock_kind.mime = "audio/flac"
        mock_kind.extension = "flac"
        mock_guess.return_value = mock_kind

        audio_meta = AudioMeta(self.test_wav)
        detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
        self.assertEqual(detected_format, "flac")

    @patch("filetype.guess")
    def test_detect_audio_format_mp4_video(self, mock_guess: Any):
        """Test _detect_audio_format correctly identifies MP4 video files"""
        # Mock filetype to return MP4 MIME type (video/mp4)
        mock_kind = MagicMock()
        mock_kind.mime = "video/mp4"
        mock_kind.extension = "mp4"
        mock_guess.return_value = mock_kind

        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    @patch("filetype.guess")
    def test_detect_audio_format_mp4_audio(self, mock_guess: Any):
        """Test _detect_audio_format correctly identifies MP4 audio files"""
        # Mock filetype to return MP4 audio MIME type
        mock_kind = MagicMock()
        mock_kind.mime = "audio/mp4"
        mock_kind.extension = "mp4"
        mock_guess.return_value = mock_kind

        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    @patch("filetype.guess")
    def test_detect_audio_format_unknown_mime(self, mock_guess: Any):
        """Test _detect_audio_format handles unknown MIME types"""
        # Mock filetype to return unknown MIME type
        mock_kind = MagicMock()
        mock_kind.mime = "application/octet-stream"
        mock_kind.extension = "bin"
        mock_guess.return_value = mock_kind

        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    @patch("filetype.guess")
    def test_detect_audio_format_none_result(self, mock_guess: Any):
        """Test _detect_audio_format handles None result from filetype"""
        # Mock filetype to return None
        mock_guess.return_value = None

        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    @patch("filetype.guess")
    def test_detect_audio_format_exception_handling(self, mock_guess: Any):
        """Test _detect_audio_format handles exceptions gracefully"""
        # Mock filetype to raise an exception
        mock_guess.side_effect = Exception("File access error")

        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    @patch("filetype.guess")
    def test_detect_audio_format_wav_variants(self, mock_guess: Any):
        """Test _detect_audio_format handles different WAV MIME type variants"""
        wav_variants = ["audio/wav", "audio/wave", "audio/x-wav"]

        for mime_type in wav_variants:
            with self.subTest(mime_type=mime_type):
                mock_kind = MagicMock()
                mock_kind.mime = mime_type
                mock_kind.extension = "wav"
                mock_guess.return_value = mock_kind

                audio_meta = AudioMeta(self.test_wav)
                detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                self.assertEqual(detected_format, "wav")

    @patch("filetype.guess")
    def test_detect_audio_format_mp3_variants(self, mock_guess: Any):
        """Test _detect_audio_format handles different MP3 MIME type variants"""
        mp3_variants = ["audio/mpeg", "audio/x-mpeg", "audio/mp3"]

        for mime_type in mp3_variants:
            with self.subTest(mime_type=mime_type):
                mock_kind = MagicMock()
                mock_kind.mime = mime_type
                mock_kind.extension = "mp3"
                mock_guess.return_value = mock_kind

                audio_meta = AudioMeta(self.test_wav)
                detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                self.assertEqual(detected_format, "mp3")

    @patch("filetype.guess")
    def test_detect_audio_format_flac_variants(self, mock_guess: Any):
        """Test _detect_audio_format handles different FLAC MIME type variants"""
        flac_variants = ["audio/flac", "audio/x-flac"]

        for mime_type in flac_variants:
            with self.subTest(mime_type=mime_type):
                mock_kind = MagicMock()
                mock_kind.mime = mime_type
                mock_kind.extension = "flac"
                mock_guess.return_value = mock_kind

                audio_meta = AudioMeta(self.test_wav)
                detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                self.assertEqual(detected_format, "flac")

    def test_set_audio_meta_with_supported_format(self):
        """Test _set_audio_meta works with supported formats"""
        audio_meta = AudioMeta(self.test_wav)
        # Should not raise an exception for supported WAV format
        self.assertIsInstance(audio_meta.nchannels, int)
        self.assertIsInstance(audio_meta.framerate, int)
        self.assertIsInstance(audio_meta.duration_in_ms, int)

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_set_audio_meta_with_unsupported_format(self, mock_detect: Any):
        """Test _set_audio_meta raises error for unsupported formats"""
        # Mock format detection to return unsupported format
        mock_detect.return_value = "mp4"

        with self.assertRaises(AssertionError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported file type", str(context.exception))
        self.assertIn("Supported: wav, mp3, flac", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_set_audio_meta_with_avi_format(self, mock_detect: Any):
        """Test _set_audio_meta raises error for AVI format"""
        # Mock format detection to return AVI format
        mock_detect.return_value = "avi"

        with self.assertRaises(AssertionError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported file type", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_set_audio_meta_with_mov_format(self, mock_detect: Any):
        """Test _set_audio_meta raises error for MOV format"""
        # Mock format detection to return MOV format
        mock_detect.return_value = "mov"

        with self.assertRaises(AssertionError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported file type", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_set_audio_meta_with_unknown_format(self, mock_detect: Any):
        """Test _set_audio_meta raises error for unknown format"""
        # Mock format detection to return unknown format
        mock_detect.return_value = "unknown"

        with self.assertRaises(AssertionError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported file type", str(context.exception))

    def test_audio_meta_properties(self):
        """Test AudioMeta properties return correct types and values"""
        audio_meta = AudioMeta(self.test_wav)

        # Test property types
        self.assertIsInstance(audio_meta.nchannels, int)
        self.assertIsInstance(audio_meta.framerate, int)
        self.assertIsInstance(audio_meta.duration_in_ms, int)

        # Test property values are positive
        self.assertGreater(audio_meta.nchannels, 0)
        self.assertGreater(audio_meta.framerate, 0)
        self.assertGreater(audio_meta.duration_in_ms, 0)

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_format_detection_integration(self, mock_detect: Any):
        """Test that format detection is properly integrated in AudioMeta initialization"""
        # Mock format detection to return MP3
        mock_detect.return_value = "mp3"

        # This should work because MP3 is supported
        audio_meta = AudioMeta(self.test_wav)
        mock_detect.assert_called_once_with(self.test_wav)
        self.assertIsInstance(audio_meta.nchannels, int)

    def test_file_with_actual_wav_format(self):
        """Test File creation with actual WAV file works correctly"""
        # This test uses the actual WAV file to ensure real format detection works
        file_obj = File(path=self.test_wav, model_tag="test_model")
        self.assertEqual(file_obj.path, self.test_wav)
        self.assertEqual(file_obj.model_tag, "test_model")

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_file_creation_with_unsupported_format(self, mock_detect: Any):
        """Test File creation succeeds but Audio creation fails when format is unsupported"""
        # Mock format detection to return unsupported format
        mock_detect.return_value = "mp4"

        # File creation should succeed (no format validation at this stage)
        file_obj = File(path=self.test_wav, model_tag="test_model")
        self.assertEqual(file_obj.path, self.test_wav)
        self.assertEqual(file_obj.model_tag, "test_model")

        # But AudioMeta creation should fail
        with self.assertRaises(AssertionError):
            AudioMeta(self.test_wav)

    def test_format_detection_error_logging(self):
        """Test that format detection errors are properly logged"""
        with patch("filetype.guess", side_effect=Exception("Test error")):
            with patch("podonos.core.base.log.error") as mock_log_error:
                with self.assertRaises(AssertionError):
                    AudioMeta(self.test_wav)
                # Should log the error
                mock_log_error.assert_called()


if __name__ == "__main__":
    unittest.main()
