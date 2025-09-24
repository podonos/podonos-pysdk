import unittest
from unittest.mock import Mock
from requests import HTTPError

from podonos.core.api import APIClient
from podonos.service.collection_service import CollectionService
from podonos.common.enum import CollectionTarget, Language
from podonos.entity.collection import CollectionEntity


class TestCollectionService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = CollectionService(self.mock_api_client)

        # Mock collection data
        self.mock_collection_data = {
            "id": "test_collection_id",
            "name": "Test Collection",
            "description": "Test Description",
            "language": Language.ENGLISH_AMERICAN.value,
            "num_required_people": 10,
            "target": CollectionTarget.AUDIO.value,
            "started_time": "2021-01-01T00:00:00Z",
            "ended_time": "2021-01-01T00:00:00Z",
            "customer_status": "DRAFT",
            "created_time": "2021-01-01T00:00:00Z",
            "updated_time": "2021-01-01T00:00:00Z",
        }

    def test_should_create_collection_successfully(self):
        # Given
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: self.mock_collection_data)

        # When
        collection = self.service.create(
            name="Test Collection",
            desc="Test Description",
            lan=Language.ENGLISH_AMERICAN.value,
            num_required_people=10,
            target=CollectionTarget.AUDIO.value,
        )

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertIsInstance(collection, CollectionEntity)
        self.assertEqual(collection.id, "test_collection_id")
        self.assertEqual(collection.name, "Test Collection")

    def test_should_raise_error_when_create_collection_with_non_en_us_language(self):
        """Test that collection creation fails with non-en-us languages including en-in"""
        # Test with en-in language (should fail)
        with self.assertRaises(Exception) as context:
            self.service.create(
                name="Test Collection EN-IN",
                desc="Test Description for Indian English",
                lan=Language.ENGLISH_INDIA.value,
                num_required_people=10,
                target=CollectionTarget.AUDIO.value,
            )

        # The error should be raised during validation
        self.assertIsNotNone(context.exception)

    def test_should_raise_error_when_create_collection_with_empty_name(self):
        # Given
        name = ""

        # When/Then
        with self.assertRaises(Exception):
            self.service.create(name=name)

    def test_should_raise_error_when_create_collection_fails(self):
        # Given
        self.mock_api_client.post.side_effect = Exception("API Error")

        # When/Then
        with self.assertRaises(HTTPError):
            self.service.create(name="Test Collection")

    def test_should_list_collections_successfully(self):
        # Given
        mock_collections = [self.mock_collection_data]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: mock_collections)

        # When
        collections = self.service.list()

        # Then
        self.mock_api_client.get.assert_called_once_with("collections")
        self.assertEqual(len(collections), 1)
        self.assertIsInstance(collections[0], CollectionEntity)
        self.assertEqual(collections[0].id, "test_collection_id")

    def test_should_raise_error_when_list_collections_fails(self):
        # Given
        self.mock_api_client.get.side_effect = Exception("API Error")

        # When/Then
        with self.assertRaises(HTTPError):
            self.service.list()


if __name__ == "__main__":
    unittest.main()
