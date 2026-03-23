import unittest

from podonos.common.enum import AIEvalType, CustomType, EvalType, Language


class TestLanguageEnum(unittest.TestCase):
    """Test cases for Language enum, specifically focusing on en-in support"""

    def test_language_enum_values(self):
        """Test that all language enum values are correctly defined"""
        self.assertEqual(Language.ENGLISH_AMERICAN.value, "en-us")
        self.assertEqual(Language.ENGLISH_BRITISH.value, "en-gb")
        self.assertEqual(Language.ENGLISH_AUSTRALIAN.value, "en-au")
        self.assertEqual(Language.ENGLISH_CANADIAN.value, "en-ca")
        self.assertEqual(Language.ENGLISH_INDIA.value, "en-in")
        self.assertEqual(Language.PORTUGUESE_PORTUGAL.value, "pt-pt")
        self.assertEqual(Language.PORTUGUESE_BRAZIL.value, "pt-br")
        self.assertEqual(Language.KOREAN.value, "ko-kr")
        self.assertEqual(Language.MANDARIN.value, "zh-cn")
        self.assertEqual(Language.SPANISH_SPAIN.value, "es-es")
        self.assertEqual(Language.SPANISH_MEXICO.value, "es-mx")
        self.assertEqual(Language.FRENCH.value, "fr-fr")
        self.assertEqual(Language.FRENCH_CANADA.value, "fr-ca")
        self.assertEqual(Language.GERMAN.value, "de-de")
        self.assertEqual(Language.JAPANESE.value, "ja-jp")
        self.assertEqual(Language.ITALIAN.value, "it-it")
        self.assertEqual(Language.POLISH.value, "pl-pl")
        self.assertEqual(Language.AUDIO.value, "audio")

    def test_language_from_value_en_in(self):
        """Test Language.from_value method specifically for en-in"""
        # Test valid en-in value
        result = Language.from_value("en-in")
        self.assertEqual(result, Language.ENGLISH_INDIA)
        self.assertEqual(result.value, "en-in")

    def test_language_from_value_all_english_variants(self):
        """Test Language.from_value method for all English variants"""
        english_variants = [
            ("en-us", Language.ENGLISH_AMERICAN),
            ("en-gb", Language.ENGLISH_BRITISH),
            ("en-au", Language.ENGLISH_AUSTRALIAN),
            ("en-ca", Language.ENGLISH_CANADIAN),
            ("en-in", Language.ENGLISH_INDIA),
        ]

        for value, expected_enum in english_variants:
            result = Language.from_value(value)
            self.assertEqual(result, expected_enum)
            self.assertEqual(result.value, value)

    def test_language_from_value_invalid(self):
        """Test Language.from_value method with invalid values"""
        invalid_values = ["invalid-lang", "en-xx", "english", ""]

        for invalid_value in invalid_values:
            with self.assertRaises(ValueError) as context:
                Language.from_value(invalid_value)
            self.assertIn("is not a valid value for Language", str(context.exception))

    def test_language_enum_comparison(self):
        """Test Language enum comparison operations"""
        # Test equality
        self.assertEqual(Language.ENGLISH_INDIA, Language.ENGLISH_INDIA)
        self.assertNotEqual(Language.ENGLISH_INDIA, Language.ENGLISH_AMERICAN)

        # Test value comparison
        self.assertEqual(Language.ENGLISH_INDIA.value, "en-in")
        self.assertNotEqual(Language.ENGLISH_INDIA.value, "en-us")

    def test_language_enum_string_representation(self):
        """Test Language enum string representation"""
        self.assertEqual(str(Language.ENGLISH_INDIA), "Language.ENGLISH_INDIA")
        self.assertEqual(repr(Language.ENGLISH_INDIA), "<Language.ENGLISH_INDIA: 'en-in'>")

    def test_language_enum_iteration(self):
        """Test that en-in is included when iterating over Language enum"""
        language_values = [lang.value for lang in Language]
        self.assertIn("en-in", language_values)

        # Verify en-in is in the correct position
        language_list = list(Language)
        en_in_index = language_list.index(Language.ENGLISH_INDIA)
        self.assertEqual(en_in_index, 4)  # Should be the 5th language (0-indexed)


class TestEvalTypeEnum(unittest.TestCase):
    """Test cases for EvalType enum"""

    def test_eval_type_enum_values(self):
        """Test that all evaluation type enum values are correctly defined"""
        self.assertEqual(EvalType.NMOS.value, "NMOS")
        self.assertEqual(EvalType.QMOS.value, "QMOS")
        self.assertEqual(EvalType.P808.value, "P808")
        self.assertEqual(EvalType.SMOS.value, "SMOS")
        self.assertEqual(EvalType.PREF.value, "PREF")
        self.assertEqual(EvalType.CMOS.value, "CMOS")
        self.assertEqual(EvalType.DMOS.value, "DMOS")
        self.assertEqual(EvalType.CSMOS.value, "CSMOS")
        self.assertEqual(EvalType.CUSTOM_SINGLE.value, "CUSTOM_SINGLE")
        self.assertEqual(EvalType.CUSTOM_DOUBLE.value, "CUSTOM_DOUBLE")
        self.assertEqual(EvalType.ASR.value, "ASR")

    def test_eval_type_get_type_method(self):
        """Test EvalType.get_type method"""
        self.assertEqual(EvalType.NMOS.get_type(), "SPEECH_NMOS")
        self.assertEqual(EvalType.QMOS.get_type(), "SPEECH_QMOS")
        self.assertEqual(EvalType.PREF.get_type(), "SPEECH_PREFERENCE")
        self.assertEqual(EvalType.CUSTOM_SINGLE.get_type(), "CUSTOM")
        self.assertEqual(EvalType.CUSTOM_DOUBLE.get_type(), "CUSTOM")

    def test_eval_type_get_type_by_batch_size(self):
        """Test EvalType.get_type_by_batch_size method"""
        self.assertEqual(EvalType.get_type_by_batch_size(1), EvalType.CUSTOM_SINGLE)
        self.assertEqual(EvalType.get_type_by_batch_size(2), EvalType.CUSTOM_DOUBLE)
        self.assertEqual(EvalType.get_type_by_batch_size(3), EvalType.CSMOS)

        with self.assertRaises(ValueError):
            EvalType.get_type_by_batch_size(4)

    def test_eval_type_classification_methods(self):
        """Test EvalType classification methods"""
        # Test single types
        single_types = EvalType.get_single_types()
        self.assertIn(EvalType.NMOS, single_types)
        self.assertIn(EvalType.QMOS, single_types)
        self.assertIn(EvalType.P808, single_types)
        self.assertIn(EvalType.CUSTOM_SINGLE, single_types)

        # Test double types
        double_types = EvalType.get_double_types()
        self.assertIn(EvalType.PREF, double_types)
        self.assertIn(EvalType.SMOS, double_types)
        self.assertIn(EvalType.CMOS, double_types)
        self.assertIn(EvalType.CUSTOM_DOUBLE, double_types)

        # Test triple types
        triple_types = EvalType.get_triple_types()
        self.assertIn(EvalType.CSMOS, triple_types)

    def test_eval_type_is_methods(self):
        """Test EvalType is_* methods"""
        self.assertTrue(EvalType.is_single("NMOS"))
        self.assertTrue(EvalType.is_double("SMOS"))
        self.assertTrue(EvalType.is_triple("CSMOS"))

        self.assertFalse(EvalType.is_single("SMOS"))
        self.assertFalse(EvalType.is_double("NMOS"))
        self.assertFalse(EvalType.is_triple("NMOS"))

    def test_eval_type_is_eval_type(self):
        """Test EvalType.is_eval_type method"""
        self.assertTrue(EvalType.is_eval_type("NMOS"))
        self.assertTrue(EvalType.is_eval_type("CUSTOM_SINGLE"))
        self.assertFalse(EvalType.is_eval_type("INVALID_TYPE"))

    def test_selected_from_template_evaluation_type_mapping(self):
        self.assertEqual(EvalType.selected_from_template_evaluation_type("SPEECH_NMOS"), EvalType.NMOS)
        self.assertEqual(EvalType.selected_from_template_evaluation_type("CUSTOM", batch_size=1), EvalType.CUSTOM_SINGLE)
        self.assertEqual(EvalType.selected_from_template_evaluation_type("CUSTOM", batch_size=2), EvalType.CUSTOM_DOUBLE)

    def test_get_supported_types_for(self):
        self.assertEqual(set(EvalType.get_supported_types_for(EvalType.NMOS)), set(EvalType.get_single_types()))
        self.assertEqual(set(EvalType.get_supported_types_for(EvalType.PREF)), set(EvalType.get_double_types()))
        self.assertEqual(set(EvalType.get_supported_types_for(EvalType.CSMOS)), set(EvalType.get_triple_types()))
        self.assertEqual(EvalType.get_supported_types_for(EvalType.RANKING), [EvalType.RANKING])

    def test_is_ranking(self):
        self.assertTrue(EvalType.is_ranking("RANKING"))
        self.assertFalse(EvalType.is_ranking("NMOS"))
        self.assertFalse(EvalType.is_ranking("PREF"))

    def test_get_ranking_types(self):
        self.assertEqual(EvalType.get_ranking_types(), [EvalType.RANKING])

    def test_selected_from_template_ranking(self):
        self.assertEqual(
            EvalType.selected_from_template_evaluation_type("SPEECH_RANKING"),
            EvalType.RANKING,
        )

    def test_custom_type_from_value_ranking(self):
        self.assertEqual(CustomType.from_value("RANKING"), CustomType.RANKING)

    def test_custom_type_values_includes_ranking(self):
        self.assertIn("RANKING", CustomType.values())

    def test_language_indonesian(self):
        self.assertEqual(Language.INDONESIAN.value, "id-id")
        self.assertEqual(Language.from_value("id-id"), Language.INDONESIAN)


class TestAIEvalTypeEnum(unittest.TestCase):
    """Test cases for AIEvalType enum"""

    def test_ai_eval_type_enum_values(self):
        """Test that all AI evaluation type enum values are correctly defined"""
        self.assertEqual(AIEvalType.ASR.value, "ASR")
        self.assertEqual(AIEvalType.ALL.value, "ALL")

    def test_ai_eval_type_from_value(self):
        """Test AIEvalType.from_value method"""
        self.assertEqual(AIEvalType.from_value("ASR"), AIEvalType.ASR)
        self.assertEqual(AIEvalType.from_value("ALL"), AIEvalType.ALL)

        with self.assertRaises(ValueError):
            AIEvalType.from_value("INVALID")

    def test_ai_eval_type_is_ai_type(self):
        """Test AIEvalType.is_ai_type method"""
        self.assertTrue(AIEvalType.is_ai_type(AIEvalType.ASR))
        self.assertTrue(AIEvalType.is_ai_type(AIEvalType.ALL))


if __name__ == "__main__":
    unittest.main()
