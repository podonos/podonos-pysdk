import unittest
from podonos.core.config import EvalConfig, EvalConfigDefault
from podonos.common.enum import Language, AIEvalType


class TestEvalConfig(unittest.TestCase):
    def setUp(self):
        self.eval_config = EvalConfig()

    def test_default_values(self):
        self.assertEqual(self.eval_config.eval_type, EvalConfigDefault.TYPE)
        self.assertEqual(self.eval_config.eval_language, EvalConfigDefault.LAN)
        self.assertEqual(self.eval_config.eval_use_annotation, EvalConfigDefault.USE_ANNOTATION)
        self.assertEqual(self.eval_config.use_loudness_normalization, EvalConfigDefault.USE_LOUDNESS_NORMALIZATION)
        self.assertEqual(self.eval_config.eval_auto_start, EvalConfigDefault.AUTO_START)
        self.assertEqual(self.eval_config.max_upload_workers, EvalConfigDefault.MAX_UPLOAD_WORKERS)

    def test_validate_eval_name(self):
        # Test with None (should generate timestamp-based name)
        name = self.eval_config._valudate_eval_name(None)  # type: ignore
        self.assertTrue(len(name) > 0)

        # Test with valid name
        valid_name = "test_evaluation"
        result = self.eval_config._valudate_eval_name(valid_name)  # type: ignore
        self.assertEqual(result, valid_name)

        # Test with invalid name (too short)
        with self.assertRaises(ValueError) as context:
            self.eval_config._valudate_eval_name("a")  # type: ignore
        self.assertEqual(str(context.exception), '"name" must be longer than 1.')

    def test_validate_eval_type(self):
        # Test valid types
        valid_types = ["NMOS", "QMOS", "SMOS", "P808", "PREF", "CSMOS", "CUSTOM_SINGLE", "CUSTOM_DOUBLE"]
        for eval_type in valid_types:
            result = self.eval_config._validate_eval_type(eval_type)  # type: ignore
            self.assertEqual(result.value, eval_type)

        # Test invalid type
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_type("INVALID_TYPE")  # type: ignore
        self.assertIn('"type" must be one of', str(context.exception))

    def test_validate_eval_language(self):
        # Test valid languages
        valid_languages = Language.values()
        for language in valid_languages:
            result = self.eval_config._validate_eval_language(language)  # type: ignore
            self.assertEqual(result.value, language)

        # Test invalid language
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_language("invalid-lang")  # type: ignore
        self.assertIn('"lan" must be one of the supported language strings', str(context.exception))

    def test_validate_eval_language_en_in_specific(self):
        """Test specifically for en-in language support"""
        # Test en-in language validation
        result = self.eval_config._validate_eval_language("en-in")  # type: ignore
        self.assertEqual(result.value, "en-in")
        self.assertEqual(result, Language.ENGLISH_INDIA)

    def test_validate_eval_ai_type(self):
        # Test valid AI type
        result = self.eval_config._validate_eval_ai_type(AIEvalType.ALL)  # type: ignore
        self.assertEqual(result, AIEvalType.ALL)

        # Test None
        result = self.eval_config._validate_eval_ai_type(None)  # type: ignore
        self.assertIsNone(result)

    def test_validate_eval_num(self):
        # Test valid numbers
        for num in [1, 5, 10, 100]:
            result = self.eval_config._validate_eval_num(num)  # type: ignore
            self.assertEqual(result, num)

        # Test invalid number
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_num(0)  # type: ignore
        self.assertEqual(str(context.exception), '"num_eval" must be >= 1.')

    def test_validate_eval_granularity(self):
        # Test valid granularity values
        for granularity in [0.5, 1.0]:
            result = self.eval_config._validate_eval_granularity(granularity)  # type: ignore
            self.assertEqual(result, granularity)

        # Test invalid granularity
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_granularity(0.3)  # type: ignore
        self.assertEqual(str(context.exception), '"granularity" must be one of 0.5 and 1.0')

    def test_validate_eval_batch_size(self):
        # Test single evaluation types
        single_types = ["NMOS", "QMOS", "P808", "CUSTOM_SINGLE"]
        for eval_type in single_types:
            result = self.eval_config._validate_eval_batch_size(eval_type)  # type: ignore
            self.assertEqual(result, 1)

        # Test double evaluation types
        double_types = ["SMOS", "PREF", "CUSTOM_DOUBLE"]
        for eval_type in double_types:
            result = self.eval_config._validate_eval_batch_size(eval_type)  # type: ignore
            self.assertEqual(result, 2)

        # Test triple evaluation type
        result = self.eval_config._validate_eval_batch_size("CSMOS")  # type: ignore
        self.assertEqual(result, 3)

    def test_validate_eval_expected_due(self):
        # Test valid due hours
        due_hours = 12
        result = self.eval_config._validate_eval_expected_due(due_hours)  # type: ignore
        self.assertTrue(isinstance(result, str))  # type: ignore

        # Test invalid due hours
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_expected_due(11)  # type: ignore
        self.assertEqual(str(context.exception), '"due_hours" must be >=12.')

    def test_set_eval_use_annotation_valid_types(self):
        valid_eval_types = ["NMOS", "QMOS", "P808", "CUSTOM_SINGLE"]
        for eval_type in valid_eval_types:
            result = self.eval_config._validate_eval_use_annotation(eval_use_annotation=True, eval_type=eval_type)  # type: ignore
            self.assertTrue(result)

    def test_set_eval_use_annotation_invalid_type(self):
        invalid_eval_type = "SMOS"
        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_use_annotation(eval_use_annotation=True, eval_type=invalid_eval_type)  # type: ignore
        self.assertEqual(str(context.exception), '"eval_type" must be one of {NMOS, QMOS, P808, CUSTOM_SINGLE} when using "use_annotation"')

    def test_to_dict(self):
        config_dict = self.eval_config.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("eval_id", config_dict)
        self.assertIn("eval_name", config_dict)
        self.assertIn("eval_type", config_dict)
        self.assertIn("eval_language", config_dict)
        self.assertIn("eval_num", config_dict)
        self.assertIn("eval_expected_due", config_dict)

    def test_to_create_request_dto(self):
        request_dto = self.eval_config.to_create_request_dto()
        self.assertIsInstance(request_dto, dict)
        self.assertIn("title", request_dto)
        self.assertIn("internal_name", request_dto)
        self.assertIn("description", request_dto)
        self.assertIn("language", request_dto)
        self.assertIn("num_required_etors", request_dto)
        self.assertIn("granularity", request_dto)
        self.assertIn("evaluation_type", request_dto)
        self.assertIn("batch_size", request_dto)
        self.assertIn("use_annotation", request_dto)
        self.assertIn("use_loudness_normalization", request_dto)
        self.assertIn("auto_start", request_dto)

    def test_to_create_from_template_request_dto(self):
        self.eval_config._eval_template_id = "template123"  # type: ignore
        request_dto = self.eval_config.to_create_from_template_request_dto()
        self.assertIsInstance(request_dto, dict)
        self.assertIn("template_id", request_dto)
        self.assertIn("title", request_dto)
        self.assertIn("description", request_dto)
        self.assertIn("num_required_etors", request_dto)


if __name__ == "__main__":
    unittest.main()
