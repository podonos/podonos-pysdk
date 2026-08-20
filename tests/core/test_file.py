import os
import unittest
from typing import Any, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from podonos.common.enum import EvalType as _ET
from glog import FailedCheckException  # type: ignore

from podonos.common.enum import QuestionFileType
from podonos.core.config import EvalConfig
from podonos.core.file import (
    AudioGroup,
    AudioMeta,
    File,
    FileTransformer,
    FileValidator,
)
from podonos.errors import InvalidFileError


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

        # When / Then
        with self.assertRaises(FailedCheckException):
            f._validate_meta_data(None)  # type: ignore

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
        meta = {
            "speaker_id": "spk1",
            "age": 30,
            "premium": True,
            "score": 9.5,
            "note": None,
        }
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
        file = File(
            path=self.test_wav,
            model_tag=model_tag,
            tags=tags,
            script=script,
            is_ref=False,
        )

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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="NMOS", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file = File(path=self.test_wav, model_tag="test_model")

        # When/Then
        file_validator.validate_file(file)

    def test_file_validator_should_validate_files_preference_successfully(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        file_validator.validate_files([file0, file1])  # Should not raise

    def test_file_validator_should_validate_files_cmos_type(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CMOS", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2", is_ref=True)

        # When/Then
        file_validator.validate_files([file0, file1])  # Should not raise

    def test_file_validator_should_validate_files_csmos_type(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CSMOS", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1")
        file1 = File(path=self.test_wav, model_tag="model2")
        file2 = File(path=self.test_wav, model_tag="model3", is_ref=True)

        # When/Then
        file_validator.validate_files([file0, file1, file2])  # Should not raise

    def test_file_validator_should_validate_files_preference_raise_error(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2")

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_files([file0, file1])

    def test_file_validator_raise_error_in_cmos_type(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CMOS", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="model1", is_ref=True)
        file1 = File(path=self.test_wav, model_tag="model2", is_ref=True)

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_files([file0, file1])

    def test_file_validator_raise_error_when_annotation_is_true_and_script_is_none(
        self,
    ):
        # Given
        eval_config = EvalConfig(
            name="test_name",
            desc="test_desc",
            type="NMOS",
            num_eval=1,
            use_annotation=True,
        )
        file_validator = FileValidator(eval_config)
        file = File(path=self.test_wav, model_tag="model1", script=None)

        # When/Then
        with self.assertRaises(ValueError):
            file_validator.validate_file(file)

    def test_file_transformer_should_transform_file_to_audio_single_stimulus(self):
        # Given
        eval_config = EvalConfig(
            name="test_name",
            desc="test_desc",
            type="NMOS",
            num_eval=1,
            use_annotation=True,
        )
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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file0 = File(
            path=self.test_wav, model_tag="test_model", meta_data={"key": "value"}
        )
        file1 = File(
            path=self.test_wav, model_tag="test_model", meta_data={"key": "value"}
        )
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file0, file1])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)
        self.assertEqual(audio_group.audios[0].path, file0.path)
        self.assertEqual(audio_group.audios[1].path, file1.path)

    def test_file_transformer_should_transform_file_to_audio_double_stimulus_with_ref(
        self,
    ):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CSMOS", num_eval=1
        )
        file0 = File(
            path=self.test_wav, model_tag="test_model", meta_data={"key": "value"}
        )
        file1 = File(path=self.test_wav, model_tag="test_model", is_ref=True)
        file2 = File(
            path=self.test_wav, model_tag="test_model", meta_data={"key": "value"}
        )
        file_transformer = FileTransformer(eval_config)

        # When
        audio_group = file_transformer.transform_into_audio_group([file0, file1, file2])

        # Then
        self.assertIsInstance(audio_group, AudioGroup)

    def test_validate_double_stimuli_model_tags_should_raise_error_for_same_model_tags(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags raises error when model tags are identical"""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(
            path=self.test_wav, model_tag="same_model", meta_data={"key": "value"}
        )
        file1 = File(
            path=self.test_wav, model_tag="same_model", meta_data={"key": "value"}
        )

        # When/Then
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_raise_error_for_case_insensitive_same_model_tags(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags raises error when model tags are same but different case"""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="google", meta_data={"key": "value"})
        file1 = File(path=self.test_wav, model_tag="openai", meta_data={"key": "value"})

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].model_tag, "google")
        self.assertEqual(result[1].model_tag, "openai")

    def test_validate_double_stimuli_model_tags_should_allow_consistent_pair_order(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags allows consistent pair ordering"""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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

    def test_validate_double_stimuli_model_tags_should_preserve_original_case(self):
        """Test that _validate_double_stimuli_model_tags preserves original case in returned files"""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(
            path=self.test_wav,
            model_tag="ModelB",
            tags=["tag1", "tag2"],
            script="script1",
            is_ref=False,
        )
        file1 = File(
            path=self.test_wav,
            model_tag="ModelA",
            tags=["tag3"],
            script="script2",
            is_ref=True,
        )

        # When
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Then
        self.assertEqual(len(result), 2)

        # Properties travel with the file through the model_tag sort
        self.assertEqual(result[0].model_tag, "ModelA")
        self.assertEqual(result[0].tags, ["tag3"])
        self.assertEqual(result[0].script, "script2")
        self.assertTrue(result[0].is_ref)

        self.assertEqual(result[1].model_tag, "ModelB")
        self.assertEqual(result[1].tags, ["tag1", "tag2"])
        self.assertEqual(result[1].script, "script1")
        self.assertFalse(result[1].is_ref)

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_handle_leading_trailing_spaces(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags works with leading/trailing spaces"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)

        file0 = File(path=self.test_wav, model_tag=" ModelA ")
        file1 = File(path=self.test_wav, model_tag="modela")

        # When/Then
        with self.assertRaises(ValueError):
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

    def test_validate_double_stimuli_model_tags_should_handle_numeric_string_tags(self):
        """Test that _validate_double_stimuli_model_tags works with numeric string model_tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="100")
        file1 = File(path=self.test_wav, model_tag="2")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        # Sorting is numeric-aware, so "2" comes before "100"
        self.assertEqual([f.model_tag for f in result], ["2", "100"])

    def test_validate_double_stimuli_model_tags_should_handle_special_symbols(self):
        """Test that _validate_double_stimuli_model_tags works with special symbols in model_tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="AAA")
        file1 = File(path=self.test_wav, model_tag="BBB")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["AAA", "BBB"])

    def test_validate_double_stimuli_model_tags_should_handle_long_strings(self):
        """Test that _validate_double_stimuli_model_tags works with long strings in model_tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="A" * 100)
        file1 = File(path=self.test_wav, model_tag="B" * 100)
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["A" * 100, "B" * 100])

    def test_validate_double_stimuli_model_tags_should_handle_unicode_emoji(self):
        """Test that _validate_double_stimuli_model_tags works with unicode letters in model_tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="모델A")
        file1 = File(path=self.test_wav, model_tag="모델B")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["모델A", "모델B"])

    @unittest.skip("Skip this test because we don't track model tag pairs")
    def test_validate_double_stimuli_model_tags_should_handle_mixed_case_and_symbols(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags works with mixed case and valid symbols in model_tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="Model-A")
        file1 = File(path=self.test_wav, model_tag="model-a")
        with self.assertRaises(ValueError) as context:
            file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertIn("model tags must differ", str(context.exception))

    def test_validate_double_stimuli_model_tags_should_allow_exactly_two_model_tags(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags allows exactly 2 model tags"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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

    def test_validate_double_stimuli_model_tags_should_reject_third_model_tag_reverse(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags rejects a third model tag in reverse order"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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

    def test_validate_double_stimuli_model_tags_should_normalize_reverse_order_of_same_pair(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags accepts a reversed pair and normalizes it"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)

        # First pair: google -> openai (should work)
        file0 = File(path=self.test_wav, model_tag="google")
        file1 = File(path=self.test_wav, model_tag="openai")
        result1 = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore

        # Second pair: openai -> google (should work - same pair, reverse order)
        file2 = File(path=self.test_wav, model_tag="openai")
        file3 = File(path=self.test_wav, model_tag="google")
        result2 = file_validator._validate_double_stimuli_model_tags(file2, file3)  # type: ignore

        # Then both calls produce the same model_tag order
        self.assertEqual(len(result1), 2)
        self.assertEqual(len(result2), 2)
        self.assertEqual(result1[0].model_tag, "google")
        self.assertEqual(result1[1].model_tag, "openai")
        self.assertEqual(result2[0].model_tag, "google")
        self.assertEqual(result2[1].model_tag, "openai")

    def test_validate_double_stimuli_model_tags_should_reject_third_model_tag_case_insensitive(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags rejects third model tag with case insensitive validation"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        file0 = File(path=self.test_wav, model_tag="가나다")
        file1 = File(path=self.test_wav, model_tag="나다라")
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual([f.model_tag for f in result], ["가나다", "나다라"])

    def test_validate_double_stimuli_model_tags_should_handle_visually_similar_unicode(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags treats visually similar but different Unicode as distinct"""
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        file_validator = FileValidator(eval_config)
        # Latin 'a' (U+0061) vs Cyrillic 'а' (U+0430) - visually identical but different codepoints
        tag1 = "model_a"  # Latin 'a'
        tag2 = "model_\u0430"  # Cyrillic 'а'

        file0 = File(path=self.test_wav, model_tag=tag1)
        file1 = File(path=self.test_wav, model_tag=tag2)

        # When/Then
        # These visually look the same but are different strings
        # Current implementation treats them as different (no homoglyph detection)
        result = file_validator._validate_double_stimuli_model_tags(file0, file1)  # type: ignore
        self.assertEqual(len(result), 2)

    def test_validate_double_stimuli_model_tags_should_handle_model_tags_with_newlines(
        self,
    ):
        """Test that _validate_double_stimuli_model_tags works with newlines in model_tags"""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
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


class TestFileScriptTags(unittest.TestCase):
    """Test cases for File.script_tags parameter"""

    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_file_default_script_tags_is_empty_list(self):
        """File without script_tags should default to []"""
        f = File(path=self.test_wav, model_tag="test_model")
        self.assertEqual(f.script_tags, [])

    def test_file_script_tags_stores_values(self):
        """File with script_tags should store them correctly"""
        f = File(path=self.test_wav, model_tag="test_model", script_tags=["a", "b"])
        self.assertEqual(f.script_tags, ["a", "b"])

    def test_file_script_tags_deduplicates(self):
        """File with duplicate script_tags should deduplicate them"""
        f = File(path=self.test_wav, model_tag="test_model", script_tags=["a", "a", "b"])
        self.assertEqual(f.script_tags, ["a", "b"])

    def test_file_script_tags_coerces_types(self):
        """File with non-string script_tags should coerce to strings"""
        f = File(path=self.test_wav, model_tag="test_model", script_tags=[1, 2.0])
        self.assertEqual(f.script_tags, ["1", "2.0"])


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

    def test_detect_audio_format_mp3(self):
        """Test _detect_audio_format correctly identifies MP3 files"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_kind = MagicMock()
            mock_kind.mime = "audio/mpeg"
            mock_kind.extension = "mp3"
            mock_guess.return_value = mock_kind

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "mp3")

    def test_detect_audio_format_flac(self):
        """Test _detect_audio_format correctly identifies FLAC files"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_kind = MagicMock()
            mock_kind.mime = "audio/flac"
            mock_kind.extension = "flac"
            mock_guess.return_value = mock_kind

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "flac")

    def test_detect_audio_format_mp4_video(self):
        """Test _detect_audio_format correctly identifies MP4 video files"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_kind = MagicMock()
            mock_kind.mime = "video/mp4"
            mock_kind.extension = "mp4"
            mock_guess.return_value = mock_kind

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "mp4")

    def test_detect_audio_format_mp4_audio(self):
        """Test _detect_audio_format correctly identifies MP4 audio files"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_kind = MagicMock()
            mock_kind.mime = "audio/mp4"
            mock_kind.extension = "mp4"
            mock_guess.return_value = mock_kind

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "mp4")

    def test_detect_audio_format_unknown_mime(self):
        """Test _detect_audio_format handles unknown MIME types by falling back to extension"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_kind = MagicMock()
            mock_kind.mime = "application/octet-stream"
            mock_kind.extension = "bin"
            mock_guess.return_value = mock_kind

            # For unknown MIME types, _detect_audio_format falls back to the extension
            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "bin")

    def test_detect_audio_format_none_result(self):
        """Test _detect_audio_format handles None result from filetype"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly
        with patch("filetype.guess") as mock_guess:
            mock_guess.return_value = None

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "unknown")

    def test_detect_audio_format_exception_handling(self):
        """Test _detect_audio_format handles exceptions gracefully"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        # Now mock and test the method directly - should return "unknown" on exception
        with patch("filetype.guess") as mock_guess:
            mock_guess.side_effect = Exception("File access error")

            detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
            self.assertEqual(detected_format, "unknown")

    def test_detect_audio_format_wav_variants(self):
        """Test _detect_audio_format handles different WAV MIME type variants"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        wav_variants = ["audio/wav", "audio/wave", "audio/x-wav"]

        for mime_type in wav_variants:
            with self.subTest(mime_type=mime_type):
                with patch("filetype.guess") as mock_guess:
                    mock_kind = MagicMock()
                    mock_kind.mime = mime_type
                    mock_kind.extension = "wav"
                    mock_guess.return_value = mock_kind

                    detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                    self.assertEqual(detected_format, "wav")

    def test_detect_audio_format_mp3_variants(self):
        """Test _detect_audio_format handles different MP3 MIME type variants"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        mp3_variants = ["audio/mpeg", "audio/x-mpeg", "audio/mp3"]

        for mime_type in mp3_variants:
            with self.subTest(mime_type=mime_type):
                with patch("filetype.guess") as mock_guess:
                    mock_kind = MagicMock()
                    mock_kind.mime = mime_type
                    mock_kind.extension = "mp3"
                    mock_guess.return_value = mock_kind

                    detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                    self.assertEqual(detected_format, "mp3")

    def test_detect_audio_format_flac_variants(self):
        """Test _detect_audio_format handles different FLAC MIME type variants"""
        # First create AudioMeta with valid file (no mock)
        audio_meta = AudioMeta(self.test_wav)

        flac_variants = ["audio/flac", "audio/x-flac"]

        for mime_type in flac_variants:
            with self.subTest(mime_type=mime_type):
                with patch("filetype.guess") as mock_guess:
                    mock_kind = MagicMock()
                    mock_kind.mime = mime_type
                    mock_kind.extension = "flac"
                    mock_guess.return_value = mock_kind

                    detected_format = audio_meta._detect_audio_format(self.test_wav)  # type: ignore
                    self.assertEqual(detected_format, "flac")

    def test_validate_audio_format_with_supported_format(self):
        """Test _validate_audio_format works with supported formats"""
        audio_meta = AudioMeta(self.test_wav)
        # Should not raise an exception for supported WAV format
        self.assertIsInstance(audio_meta.nchannels, int)
        self.assertIsInstance(audio_meta.framerate, int)
        self.assertIsInstance(audio_meta.duration_in_ms, int)

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_validate_audio_format_with_unsupported_format(self, mock_detect: Any):
        """Test _validate_audio_format raises error for unsupported formats"""
        # Mock format detection to return unsupported format
        mock_detect.return_value = "mp4"

        with self.assertRaises(InvalidFileError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported audio format", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_validate_audio_format_with_avi_format(self, mock_detect: Any):
        """Test _validate_audio_format raises error for AVI format"""
        # Mock format detection to return AVI format
        mock_detect.return_value = "avi"

        with self.assertRaises(InvalidFileError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported audio format", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_validate_audio_format_with_mov_format(self, mock_detect: Any):
        """Test _validate_audio_format raises error for MOV format"""
        # Mock format detection to return MOV format
        mock_detect.return_value = "mov"

        with self.assertRaises(InvalidFileError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported audio format", str(context.exception))

    @patch("podonos.core.file.AudioMeta._detect_audio_format")
    def test_validate_audio_format_with_unknown_format(self, mock_detect: Any):
        """Test _validate_audio_format raises error for unknown format"""
        # Mock format detection to return unknown format
        mock_detect.return_value = "unknown"

        with self.assertRaises(InvalidFileError) as context:
            AudioMeta(self.test_wav)
        self.assertIn("Unsupported audio format", str(context.exception))

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
        # Mock format detection to return WAV (must match the file extension)
        mock_detect.return_value = "wav"

        # This should work because WAV is supported and matches the .wav extension
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

        # But AudioMeta creation should fail with InvalidFileError
        with self.assertRaises(InvalidFileError):
            AudioMeta(self.test_wav)

    def test_format_detection_error_logging(self):
        """Test that format detection errors result in 'unknown' format and proper handling"""
        with patch("filetype.guess", side_effect=Exception("Test error")):
            # When filetype.guess fails, _detect_audio_format returns "unknown"
            # which is an unsupported format, so InvalidFileError is raised
            with self.assertRaises(InvalidFileError) as context:
                AudioMeta(self.test_wav)
            self.assertIn("Unsupported audio format", str(context.exception))


class TestDoubleStimuliOrderInGroup(unittest.TestCase):
    """order_in_group must be stable per model_tag, whatever order the caller passes.

    The platform resolves "Model A" by order_in_group and shuffles the on-screen
    order itself, so a model_tag landing at different orders in different groups
    mixes two models into one aggregate and is rejected at checkout.
    """

    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.test_wav = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def _orders(self, validator, transformer, files: List[File]):
        """Run one add_files-equivalent group and return {model_tag: order_in_group}."""
        validated = validator.validate_files(list(files))
        audio_group = transformer.transform_into_audio_group(validated)
        return {a.model_tag: a.order_in_group for a in audio_group.audios}

    def test_reversed_argument_order_produces_same_order_in_group(self):
        # Given: a caller that shuffles which model goes first on each trial
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        validator = FileValidator(eval_config)
        transformer = FileTransformer(eval_config)

        # When
        first = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model_b"),
                File(path=self.test_wav, model_tag="model_a"),
            ],
        )
        second = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model_a"),
                File(path=self.test_wav, model_tag="model_b"),
            ],
        )

        # Then
        self.assertEqual(first, {"model_a": 0, "model_b": 1})
        self.assertEqual(first, second)

    def test_model_tag_sort_is_case_insensitive_and_numeric_aware(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )

        # When: numeric-aware, model_2 sorts before model_10
        numeric = FileValidator(eval_config)._validate_double_stimuli_model_tags(  # type: ignore
            File(path=self.test_wav, model_tag="model_10"),
            File(path=self.test_wav, model_tag="model_2"),
        )

        # And: case-insensitive, Zebra sorts after apple
        case = FileValidator(eval_config)._validate_double_stimuli_model_tags(  # type: ignore
            File(path=self.test_wav, model_tag="Zebra"),
            File(path=self.test_wav, model_tag="apple"),
        )

        # Then
        self.assertEqual([f.model_tag for f in numeric], ["model_2", "model_10"])
        self.assertEqual([f.model_tag for f in case], ["apple", "Zebra"])

    def test_case_only_difference_still_produces_stable_order(self):
        """The natsort key folds case, so the raw tag has to break the tie."""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        validator = FileValidator(eval_config)
        transformer = FileTransformer(eval_config)

        # When
        first = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="Model"),
                File(path=self.test_wav, model_tag="model"),
            ],
        )
        second = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model"),
                File(path=self.test_wav, model_tag="Model"),
            ],
        )

        # Then
        self.assertEqual(first, second)

    def test_leading_zero_difference_still_produces_stable_order(self):
        """The natsort key reads m01 and m1 as the same number, so it ties."""
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="PREF", num_eval=1
        )
        validator = FileValidator(eval_config)
        transformer = FileTransformer(eval_config)

        # When
        first = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="m01"),
                File(path=self.test_wav, model_tag="m1"),
            ],
        )
        second = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="m1"),
                File(path=self.test_wav, model_tag="m01"),
            ],
        )

        # Then
        self.assertEqual(first, second)

    def test_cmos_keeps_reference_last_regardless_of_argument_order(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CMOS", num_eval=1
        )
        validator = FileValidator(eval_config)
        transformer = FileTransformer(eval_config)

        # When
        ref_last = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model_a"),
                File(path=self.test_wav, model_tag="ground_truth", is_ref=True),
            ],
        )
        ref_first = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="ground_truth", is_ref=True),
                File(path=self.test_wav, model_tag="model_a"),
            ],
        )

        # Then: the documented (stimulus, reference) call keeps its stored order
        self.assertEqual(ref_last, {"model_a": 0, "ground_truth": 1})
        self.assertEqual(ref_last, ref_first)

    def test_csmos_keeps_reference_last_regardless_of_stimulus_order(self):
        # Given
        eval_config = EvalConfig(
            name="test_name", desc="test_desc", type="CSMOS", num_eval=1
        )
        validator = FileValidator(eval_config)
        transformer = FileTransformer(eval_config)

        # When
        first = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model_b"),
                File(path=self.test_wav, model_tag="model_a"),
                File(path=self.test_wav, model_tag="ground_truth", is_ref=True),
            ],
        )
        second = self._orders(
            validator,
            transformer,
            [
                File(path=self.test_wav, model_tag="model_a"),
                File(path=self.test_wav, model_tag="model_b"),
                File(path=self.test_wav, model_tag="ground_truth", is_ref=True),
            ],
        )

        # Then: reference stays at 2 even though it sorts first alphabetically
        self.assertEqual(first, {"model_a": 0, "model_b": 1, "ground_truth": 2})
        self.assertEqual(first, second)


class TestFileRanking(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.audio_path = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def test_ranking_accepts_two_files_with_consistent_order(self):
        """Test RANKING accepts two files and enforces consistent order across groups"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # First group: A, B
        g1 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]
        v1 = validator.validate_files(list(g1))
        assert [f.model_tag for f in v1] == ["A", "B"]

        # Second group: same order A, B (should pass)
        g2 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]
        v2 = validator.validate_files(list(g2))
        assert [f.model_tag for f in v2] == ["A", "B"]

    def test_ranking_accepts_three_or_more_files(self):
        """Test RANKING accepts three or more files in a group"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # Group with 3 files
        g1 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
            File(path=self.audio_path, model_tag="C"),
        ]
        v1 = validator.validate_files(list(g1))
        assert [f.model_tag for f in v1] == ["A", "B", "C"]

        # Second group: same order and size (should pass)
        g2 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
            File(path=self.audio_path, model_tag="C"),
        ]
        v2 = validator.validate_files(list(g2))
        assert [f.model_tag for f in v2] == ["A", "B", "C"]

    def test_ranking_rejects_single_file(self):
        """Test RANKING rejects a group with only one file"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files([File(path=self.audio_path, model_tag="A")])
        assert "RANKING requires at least two files in a group" in str(context.value)

    def test_ranking_rejects_inconsistent_order(self):
        """Test RANKING rejects groups with inconsistent model_tag order"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # First group: A, B
        g1 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]
        validator.validate_files(list(g1))

        # Second group: B, A (reversed order - should fail)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="B"),
                    File(path=self.audio_path, model_tag="A"),
                ]
            )
        assert "identical model_tag order" in str(context.value)

    def test_ranking_rejects_inconsistent_size(self):
        """Test RANKING rejects groups with inconsistent size"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # First group: 2 files
        g1 = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]
        validator.validate_files(list(g1))

        # Second group: 3 files (should fail)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="A"),
                    File(path=self.audio_path, model_tag="B"),
                    File(path=self.audio_path, model_tag="C"),
                ]
            )
        assert "consistent group size" in str(context.value)

    def test_ranking_rejects_reference_file_first_position(self):
        """Test RANKING rejects is_ref=True in first position"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="A", is_ref=True),
                    File(path=self.audio_path, model_tag="B"),
                ]
            )
        assert "cannot include reference files" in str(context.value)

    def test_ranking_rejects_reference_file_second_position(self):
        """Test RANKING rejects is_ref=True in second position"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="A"),
                    File(path=self.audio_path, model_tag="B", is_ref=True),
                ]
            )
        assert "cannot include reference files" in str(context.value)

    def test_ranking_rejects_reference_file_middle_position(self):
        """Test RANKING rejects is_ref=True in middle position"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="A"),
                    File(path=self.audio_path, model_tag="B", is_ref=True),
                    File(path=self.audio_path, model_tag="C"),
                ]
            )
        assert "cannot include reference files" in str(context.value)

    def test_ranking_rejects_all_reference_files(self):
        """Test RANKING rejects when all files have is_ref=True"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="A", is_ref=True),
                    File(path=self.audio_path, model_tag="B", is_ref=True),
                ]
            )
        assert "cannot include reference files" in str(context.value)

    def test_ranking_rejects_duplicate_model_tags_exact_match(self):
        """Test RANKING rejects duplicate model_tags (exact match)"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="AWS"),
                    File(path=self.audio_path, model_tag="AWS"),
                ]
            )
        assert "unique model_tags within a group" in str(context.value)
        assert "Duplicate found: 'AWS'" in str(context.value)

    def test_ranking_rejects_duplicate_model_tags_case_insensitive(self):
        """Test RANKING rejects duplicate model_tags (case-insensitive)"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # Test AWS vs aws
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="AWS"),
                    File(path=self.audio_path, model_tag="aws"),
                ]
            )
        assert "unique model_tags within a group" in str(context.value)
        assert "case-insensitive" in str(context.value)

    def test_ranking_rejects_duplicate_model_tags_mixed_case(self):
        """Test RANKING rejects duplicate model_tags with mixed case"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # Test OpenAI vs openai vs OPENAI
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="OpenAI"),
                    File(path=self.audio_path, model_tag="Google"),
                    File(path=self.audio_path, model_tag="openai"),
                ]
            )
        assert "unique model_tags within a group" in str(context.value)
        assert "Duplicate found: 'openai'" in str(context.value)

    def test_ranking_rejects_duplicate_in_three_files(self):
        """Test RANKING rejects duplicate model_tags in a group of three"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # First and last have same tag (case-insensitive)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [
                    File(path=self.audio_path, model_tag="ModelA"),
                    File(path=self.audio_path, model_tag="ModelB"),
                    File(path=self.audio_path, model_tag="modela"),
                ]
            )
        assert "unique model_tags within a group" in str(context.value)

    def test_ranking_accepts_unique_model_tags_different_cases(self):
        """Test RANKING accepts truly unique model_tags even with different casing in names"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # These should pass - different model tags
        files: List[Optional[File]] = [
            File(path=self.audio_path, model_tag="AWS"),
            File(path=self.audio_path, model_tag="OpenAI"),
            File(path=self.audio_path, model_tag="Google"),
        ]
        result = validator.validate_files(files)
        assert len(result) == 3
        assert [f.model_tag for f in result] == ["AWS", "OpenAI", "Google"]

    def test_ranking_duplicate_check_across_multiple_groups(self):
        """Test RANKING duplicate check works correctly across multiple groups"""
        from podonos.common.enum import EvalType as _EvalType
        from podonos.core.config import EvalConfig
        from podonos.core.file import File, FileValidator

        cfg = EvalConfig(type=_EvalType.CUSTOM_DOUBLE.value)
        cfg._eval_type = _EvalType.RANKING  # type: ignore
        validator = FileValidator(cfg)

        # First group: A, B, C (should pass)
        files1: List[Optional[File]] = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
            File(path=self.audio_path, model_tag="C"),
        ]
        validator.validate_files(files1)

        # Second group: A, A, C (should fail - duplicate in second group)
        files2: List[Optional[File]] = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="a"),
            File(path=self.audio_path, model_tag="C"),
        ]
        with pytest.raises(ValueError) as context:
            validator.validate_files(files2)
        assert "unique model_tags within a group" in str(context.value)


class TestFileRankingRef(unittest.TestCase):
    """RANKING_REF: exactly one per-group reference, stored last."""

    def setUp(self):
        self.test_dir = os.path.dirname(__file__)
        self.audio_path = os.path.join(self.test_dir, "speech_two_ch1.wav")

    def _validator(self, eval_type):
        from podonos.core.config import EvalConfig
        from podonos.core.file import FileValidator

        cfg = EvalConfig(type=_ET.CUSTOM_DOUBLE.value)
        cfg._eval_type = eval_type  # type: ignore
        return FileValidator(cfg)

    def _f(self, model_tag, is_ref=False):
        from podonos.core.file import File

        return File(path=self.audio_path, model_tag=model_tag, is_ref=is_ref)

    def test_accepts_group_with_one_reference(self):
        validator = self._validator(_ET.RANKING_REF)
        valid = validator.validate_files(
            [self._f("A"), self._f("B"), self._f("R", is_ref=True)]
        )
        assert [f.model_tag for f in valid] == ["A", "B", "R"]
        assert [f.is_ref for f in valid] == [False, False, True]

    def test_reference_position_in_argument_list_does_not_matter(self):
        """The reference may sit anywhere; the stored order must be identical.

        One validator across all three calls on purpose: alternating the argument
        position only stays safe because the cross-group order check covers stimuli
        only. A fresh validator per iteration would compare each group against empty
        state and prove nothing.
        """
        expected = ["A", "B", "R"]
        validator = self._validator(_ET.RANKING_REF)
        for group in (
            [self._f("R", is_ref=True), self._f("A"), self._f("B")],
            [self._f("A"), self._f("R", is_ref=True), self._f("B")],
            [self._f("A"), self._f("B"), self._f("R", is_ref=True)],
        ):
            valid = validator.validate_files(group)
            assert [f.model_tag for f in valid] == expected
            assert valid[-1].is_ref is True

    def test_rejects_group_without_reference(self):
        validator = self._validator(_ET.RANKING_REF)
        with pytest.raises(ValueError) as context:
            validator.validate_files([self._f("A"), self._f("B")])
        assert "exactly one reference" in str(context.value)

    def test_rejects_group_with_two_references(self):
        validator = self._validator(_ET.RANKING_REF)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [self._f("A"), self._f("B"), self._f("R1", is_ref=True), self._f("R2", is_ref=True)]
            )
        assert "exactly one reference" in str(context.value)

    def test_rejects_single_stimulus_with_reference(self):
        validator = self._validator(_ET.RANKING_REF)
        with pytest.raises(ValueError) as context:
            validator.validate_files([self._f("A"), self._f("R", is_ref=True)])
        assert "at least two" in str(context.value)

    def test_plain_ranking_still_rejects_a_reference(self):
        """The only client-side guard: the SDK's upload path has no server-side
        REFERENCE_NOT_ALLOWED_FOR_EVALUATION_TYPE equivalent."""
        validator = self._validator(_ET.RANKING)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [self._f("A"), self._f("B"), self._f("R", is_ref=True)]
            )
        assert "cannot include reference files" in str(context.value)

    def test_rejects_reference_tag_colliding_with_a_stimulus_tag(self):
        """Caught here rather than as an unexplained order error at upload."""
        validator = self._validator(_ET.RANKING_REF)
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [self._f("A"), self._f("B"), self._f("a", is_ref=True)]
            )
        assert "unique model_tags within a group" in str(context.value)

    def test_rejects_a_different_reference_tag_per_group(self):
        """One reference model per evaluation, not one per script.

        The backend accepts distinct tags at upload -- its check is first-seen per
        tag and the reference always sits at the same order -- but the summary
        screen aggregates by model_tag, so N tags render as N one-file reference
        rows. Nothing server-side rejects it, so this is the only guard.
        """
        validator = self._validator(_ET.RANKING_REF)
        validator.validate_files([self._f("A"), self._f("B"), self._f("ref_s1", is_ref=True)])
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [self._f("A"), self._f("B"), self._f("ref_s2", is_ref=True)]
            )
        assert "same reference model_tag in every group" in str(context.value)

    def test_allows_the_same_reference_tag_across_groups(self):
        validator = self._validator(_ET.RANKING_REF)
        validator.validate_files([self._f("A"), self._f("B"), self._f("R", is_ref=True)])
        valid = validator.validate_files([self._f("A"), self._f("B"), self._f("R", is_ref=True)])
        assert [f.model_tag for f in valid] == ["A", "B", "R"]

    def test_rejects_inconsistent_stimulus_order_across_groups(self):
        validator = self._validator(_ET.RANKING_REF)
        validator.validate_files([self._f("A"), self._f("B"), self._f("R", is_ref=True)])
        with pytest.raises(ValueError) as context:
            validator.validate_files([self._f("B"), self._f("A"), self._f("R", is_ref=True)])
        assert "identical model_tag order" in str(context.value)

    def test_rejects_inconsistent_group_size(self):
        validator = self._validator(_ET.RANKING_REF)
        validator.validate_files([self._f("A"), self._f("B"), self._f("R", is_ref=True)])
        with pytest.raises(ValueError) as context:
            validator.validate_files(
                [self._f("A"), self._f("B"), self._f("C"), self._f("R", is_ref=True)]
            )
        assert "consistent group size" in str(context.value)

    def test_transform_stores_the_reference_last_as_ref_type(self):
        from podonos.common.enum import QuestionFileType
        from podonos.core.config import EvalConfig
        from podonos.core.file import FileTransformer

        cfg = EvalConfig(type=_ET.CUSTOM_DOUBLE.value)
        cfg._eval_type = _ET.RANKING_REF  # type: ignore
        validator = self._validator(_ET.RANKING_REF)

        valid = validator.validate_files(
            [self._f("R", is_ref=True), self._f("A"), self._f("B")]
        )
        group = FileTransformer(cfg).transform_into_audio_group(valid)

        refs = [a for a in group.audios if a.type == QuestionFileType.REF]
        assert len(refs) == 1
        assert refs[0].order_in_group == max(a.order_in_group for a in group.audios)
        assert [a.order_in_group for a in group.audios] == [0, 1, 2]
        assert [a.model_tag for a in group.audios] == ["A", "B", "R"]


if __name__ == "__main__":
    unittest.main()
