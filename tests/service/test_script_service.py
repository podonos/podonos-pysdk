import unittest
from unittest.mock import Mock
from uuid import uuid4
from typing import Any, Dict
from typing import List
from requests import HTTPError

from podonos.core.api import APIClient
from podonos.service.script_service import ScriptService
from podonos.common.enum import SpeechStyle, SpeechEmotion, SpeechSpeed
from podonos.entity.script import ScriptEntity


class TestScriptService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_api_client = Mock(spec=APIClient)
        self.service = ScriptService(self.mock_api_client)

        # Mock script data
        self.mock_script_data: Dict[str, Any] = {
            "id": str(uuid4()),
            "collection_id": str(uuid4()),
            "text": "Hello, this is a test script",
            "estimated_duration": 375,
            "required_count": 7,
            "collected_count": 0,
            "speech_style": SpeechStyle.NONE.value,
            "emotion": SpeechEmotion.NEUTRAL.value,
            "speed": SpeechSpeed.NORMAL.value,
            "meta_data": {},
            "created_time": "2024-03-24T09:49:14.861601Z",
            "updated_time": "2024-03-24T09:49:14.861601Z",
        }

    def test_should_create_scripts_successfully(self):
        # Given
        collection_id = str(uuid4())
        texts = ["Hello", "This is test"]
        mock_response: List[Dict[str, Any]] = [self.mock_script_data, {**self.mock_script_data, "id": str(uuid4()), "text": "This is test"}]
        self.mock_api_client.post.return_value = Mock(status_code=200, json=lambda: mock_response)

        # When
        scripts = self.service.create_all(collection_id=collection_id, texts=texts)

        # Then
        self.mock_api_client.post.assert_called_once()
        self.assertEqual(len(scripts), 2)
        self.assertIsInstance(scripts[0], ScriptEntity)
        self.assertEqual(scripts[0].id, self.mock_script_data["id"])
        self.assertEqual(scripts[0].text, "Hello, this is a test script")
        self.assertEqual(scripts[0].speech_style, SpeechStyle.NONE)
        self.assertEqual(scripts[0].emotion, SpeechEmotion.NEUTRAL)
        self.assertEqual(scripts[0].speed, SpeechSpeed.NORMAL)

    def test_should_raise_error_when_create_scripts_with_empty_collection_id(self):
        # Given
        collection_id = ""
        texts = ["Hello"]

        # When/Then
        with self.assertRaises(ValueError):
            self.service.create_all(collection_id=collection_id, texts=texts)

    def test_should_raise_error_when_create_scripts_with_empty_texts(self):
        # Given
        collection_id = str(uuid4())
        texts: List[str] = []

        # When/Then
        with self.assertRaises(HTTPError) as context:
            self.service.create_all(collection_id=collection_id, texts=texts)
        self.assertIn("At least one text is required", str(context.exception))

    def test_should_raise_error_when_create_scripts_fails(self):
        # Given
        collection_id = str(uuid4())
        texts: List[str] = ["Hello"]
        self.mock_api_client.post.side_effect = Exception("API Error")

        # When/Then
        with self.assertRaises(HTTPError):
            self.service.create_all(collection_id=collection_id, texts=texts)

    def test_should_list_scripts_successfully(self):
        # Given
        script_id = self.mock_script_data["id"]
        collection_id = self.mock_script_data["collection_id"]
        mock_scripts: List[Dict[str, Any]] = [self.mock_script_data]
        self.mock_api_client.get.return_value = Mock(status_code=200, json=lambda: mock_scripts)

        # When
        scripts = self.service.list(collection_id=collection_id)

        # Then
        self.mock_api_client.get.assert_called_once_with(f"scripts?collection-id={collection_id}")
        self.assertEqual(len(scripts), 1)
        self.assertIsInstance(scripts[0], ScriptEntity)
        self.assertEqual(scripts[0].id, script_id)
        self.assertEqual(scripts[0].collection_id, collection_id)
        self.assertEqual(scripts[0].text, "Hello, this is a test script")

    def test_should_raise_error_when_list_scripts_fails(self):
        # Given
        self.mock_api_client.get.side_effect = Exception("API Error")

        # When/Then
        with self.assertRaises(HTTPError):
            self.service.list(collection_id=str(uuid4()))


if __name__ == "__main__":
    unittest.main()
