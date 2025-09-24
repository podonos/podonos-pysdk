import unittest
from typing import Dict, Any
from podonos.core.collection import CollectionCreateRequestDto
from podonos.common.enum import CollectionTarget, Language


class TestCollectionCreateRequestDto(unittest.TestCase):
    """Test cases for CollectionCreateRequestDto, focusing on language support"""

    def test_default_values(self):
        """Test default values for CollectionCreateRequestDto"""
        dto = CollectionCreateRequestDto(name="Test Collection")

        self.assertEqual(dto.name, "Test Collection")
        self.assertIsNone(dto.description)
        self.assertEqual(dto.language, Language.ENGLISH_AMERICAN.value)
        self.assertEqual(dto.num_required_people, 10)
        self.assertEqual(dto.target, CollectionTarget.AUDIO)

    def test_get_language_method(self):
        """Test get_language method"""
        dto = CollectionCreateRequestDto(name="Test", language="en-us")
        self.assertEqual(dto.get_language(), Language.ENGLISH_AMERICAN)

        dto = CollectionCreateRequestDto(name="Test", language="en-in")
        self.assertEqual(dto.get_language(), Language.ENGLISH_INDIA)

    def test_to_create_request_dto(self):
        """Test to_create_request_dto method"""
        dto = CollectionCreateRequestDto(
            name="Test Collection", description="Test Description", language="en-in", num_required_people=20, target=CollectionTarget.AUDIO
        )

        result: Dict[str, Any] = dto.to_create_request_dto()

        self.assertEqual(result["name"], "Test Collection")
        self.assertEqual(result["description"], "Test Description")
        self.assertEqual(result["language"], "en-in")
        self.assertEqual(result["num_required_people"], 20)
        self.assertEqual(result["target"], "AUDIO")

    def test_from_dict_valid_en_us(self):
        """Test from_dict method with valid en-us language"""
        dto = CollectionCreateRequestDto.from_dict(
            name="Test Collection", description="Test Description", language="en-us", num_required_people=15, target="AUDIO"
        )

        self.assertEqual(dto.name, "Test Collection")
        self.assertEqual(dto.description, "Test Description")
        self.assertEqual(dto.language, "en-us")
        self.assertEqual(dto.num_required_people, 15)
        self.assertEqual(dto.target, CollectionTarget.AUDIO)

    def test_from_dict_invalid_language_en_in(self):
        """Test from_dict method with en-in language (should fail)"""
        with self.assertRaises(ValueError) as context:
            CollectionCreateRequestDto.from_dict(
                name="Test Collection", description="Test Description", language="en-in", num_required_people=15, target="AUDIO"  # This should fail
            )

        self.assertIn("The language of the collection must be en-us", str(context.exception))

    def test_from_dict_invalid_language_other(self):
        """Test from_dict method with other invalid languages"""
        invalid_languages = ["en-gb", "ko-kr", "zh-cn", "es-es", "fr-fr"]

        for lang in invalid_languages:
            with self.assertRaises(ValueError) as context:
                CollectionCreateRequestDto.from_dict(
                    name="Test Collection",
                    language=lang,
                )
            self.assertIn("The language of the collection must be en-us", str(context.exception))

    def test_from_dict_empty_name(self):
        """Test from_dict method with empty name"""
        with self.assertRaises(ValueError) as context:
            CollectionCreateRequestDto.from_dict(name="")

        self.assertIn("The name of the collection is required", str(context.exception))

    def test_from_dict_invalid_num_required_people(self):
        """Test from_dict method with invalid num_required_people"""
        with self.assertRaises(ValueError) as context:
            CollectionCreateRequestDto.from_dict(name="Test Collection", num_required_people=0)

        self.assertIn("The number of required people must be greater than 0", str(context.exception))

    def test_from_dict_invalid_target(self):
        """Test from_dict method with invalid target"""
        with self.assertRaises(ValueError) as context:
            CollectionCreateRequestDto.from_dict(name="Test Collection", target="INVALID_TARGET")

        self.assertIn("The target of the collection must be one of the following: AUDIO", str(context.exception))

    def test_from_dict_default_values(self):
        """Test from_dict method with default values"""
        dto = CollectionCreateRequestDto.from_dict(name="Test Collection")

        self.assertEqual(dto.name, "Test Collection")
        self.assertIsNone(dto.description)
        self.assertEqual(dto.language, "en-us")
        self.assertEqual(dto.num_required_people, 10)
        self.assertEqual(dto.target, CollectionTarget.AUDIO)


if __name__ == "__main__":
    unittest.main()
