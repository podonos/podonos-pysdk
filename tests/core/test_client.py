import os
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch, MagicMock
from typing import Any
from uuid import uuid4
from requests import Response
import json as pyjson

import podonos
from podonos.core.client import Client
from podonos.core.evaluator import Evaluator
from podonos.core.api import APIClient


def _make_response(text: Any = None, json_data: Any = None, status_code: int = 200) -> Response:
    resp = Response()
    resp.status_code = status_code
    if json_data is not None:
        resp._content = pyjson.dumps(json_data).encode("utf-8")
        resp.headers["Content-Type"] = "application/json"
    elif text is not None:
        resp._content = str(text).encode("utf-8")
    else:
        resp._content = b""
    return resp


def mocked_requests_post(*args: Any, **kwargs: Any):
    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = dict(
            id=str(uuid4()),
            title="mock_title",
            internal_name="mock_internal_name",
            batch_size=1,
            description="mock_desc",
            status="mock_status",
            created_time="2024-05-21T06:18:09.659Z",
            updated_time="2024-05-21T06:18:09.659Z",
        )
        return _make_response(json_data=evaluation_list, status_code=200)

    return _make_response(status_code=404)


# Mocks HTTP GET request.
def mocked_requests_get(*args: Any, **kwargs: Any):
    if "/customers/verify/api-key" in args[0]:
        # API key verification
        return _make_response(text="true", status_code=200)

    if "/version/sdk" in args[0]:
        # SDK versions
        version_response = dict(latest="0.1.5", recommended="0.1.4", minimum="0.1.0")
        return _make_response(json_data=version_response, status_code=200)

    if "/evaluations" in args[0] and "/stats" in args[0]:
        # Stats by id
        evaluation_stats = [
            dict(
                files=[{"name": "tr16.wav", "model_tag": "my_model", "tags": ["generated"], "type": "A"}],
                question={
                    "title": "Attending **ONLY to the BACKGROUND (noise or other speakers' voices)**, "
                    "select the category which best describes the sample you just heard.",
                    "order": 0,
                },
                mean=3.4,
                median=3.5,
                std=1.07,
                option_a=True,
                option_b=False,
            )
        ]
        return _make_response(json_data=evaluation_stats, status_code=200)

    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = [
            dict(
                id=str(uuid4()),
                title="mock_title",
                internal_name="mock_internal_name",
                description="mock_desc",
                batch_size=1,
                status="mock_status",
                created_time="2024-05-21T06:18:09.659Z",
                updated_time="2024-05-21T06:18:09.659Z",
            )
        ]
        return _make_response(json_data=evaluation_list, status_code=200)

    if "/templates" in args[0]:
        eval_template_info = dict(
            id=str(uuid4()),
            code="mock_code",
            title="mock_title",
            description="mock_description",
            batch_size=1,
            use_annotation=False,
            use_power_normalization=True,
            language="en-us",
            created_time="2025-05-21T06:18:09.659Z",
            updated_time="2025-05-28T13:59:12.123Z",
        )
        return _make_response(json_data=eval_template_info, status_code=200)

    return _make_response(status_code=404)


class TestEvaluationClient(unittest.TestCase):

    def setUp(self):
        self.valid_api_key = "1234567890"
        # Single stimulus
        self.single_template_json = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Audio Quality Assessment",
                    "description": "Please evaluate the overall quality of the audio",
                    "options": [
                        {"label_text": "Very Poor"},
                        {"label_text": "Poor"},
                        {"label_text": "Fair"},
                        {"label_text": "Good"},
                        {"label_text": "Excellent"},
                    ],
                },
                {
                    "type": "NON_SCORED",
                    "question": "Audio Characteristics",
                    "description": "Please select all audio characteristics that you hear",
                    "options": [{"label_text": "Background Noise"}, {"label_text": "Echo"}, {"label_text": "Distortion"}],
                    "allow_multiple": True,
                    "has_other": True,
                    "has_none": False,
                },
            ],
            "instructions": [
                {
                    "type": "WARNING",
                    "instruction": "Evaluation Guidelines",
                    "description": "Important points to consider when evaluating audio",
                }
            ],
        }

        # Double stimulus
        self.double_template_json = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Audio Quality Comparison",
                    "description": "Please compare the quality between two audio samples",
                    "scale": 5,
                    "anchor_label": {"title": "Preference", "label_text": {"left": "Better", "right": "Better"}},
                }
            ]
        }

    def create_temp_json_file(self, is_single: bool = True) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.single_template_json if is_single else self.double_template_json, f)
            return f.name

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_single_stimulus_evaluator_creation(self, mock_get: Any, mock_post: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "good_test"
        desc = "detailed description"
        type = "NMOS"
        lan = "it-it"
        granularity = 1.0
        num_eval = 8
        due_hours = 12
        auto_start = False
        max_upload_workers = 10
        etor = self._mock_client.create_evaluator(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            granularity=granularity,
            num_eval=num_eval,
            due_hours=due_hours,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_double_stimuli_evaluator_creation(self, mock_get: Any, mock_post: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "good_test"
        desc = "detailed description"
        type = "PREF"
        lan = "ko-kr"
        granularity = 1.0
        num_eval = 5
        due_hours = 12
        auto_start = False
        max_upload_workers = 10
        etor = self._mock_client.create_evaluator(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            granularity=granularity,
            num_eval=num_eval,
            due_hours=due_hours,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_single_stimulus_evaluator_creation_with_en_in_language(self, mock_get: Any, mock_post: Any):
        """Test single stimulus evaluator creation with en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "en_in_test"
        desc = "detailed description for Indian English"
        type = "NMOS"
        lan = "en-in"  # Indian English
        granularity = 1.0
        num_eval = 8
        due_hours = 12
        auto_start = False
        max_upload_workers = 10
        etor = self._mock_client.create_evaluator(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            granularity=granularity,
            num_eval=num_eval,
            due_hours=due_hours,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_double_stimuli_evaluator_creation_with_en_in_language(self, mock_get: Any, mock_post: Any):
        """Test double stimuli evaluator creation with en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "en_in_double_test"
        desc = "detailed description for Indian English double stimuli"
        type = "PREF"
        lan = "en-in"  # Indian English
        granularity = 1.0
        num_eval = 5
        due_hours = 12
        auto_start = False
        max_upload_workers = 10
        etor = self._mock_client.create_evaluator(
            name=name,
            desc=desc,
            type=type,
            lan=lan,
            granularity=granularity,
            num_eval=num_eval,
            due_hours=due_hours,
            auto_start=auto_start,
            max_upload_workers=max_upload_workers,
        )
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_evaluator_creation_with_all_eval_types_en_in_language(self, mock_get: Any, mock_post: Any):
        """Test evaluator creation with all evaluation types using en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)

        # Test all evaluation types with en-in language
        eval_types = ["NMOS", "QMOS", "SMOS", "P808", "PREF", "CSMOS", "CUSTOM_SINGLE", "CUSTOM_DOUBLE"]

        for eval_type in eval_types:
            etor = self._mock_client.create_evaluator(
                name=f"en_in_{eval_type.lower()}_test",
                desc=f"Test {eval_type} evaluation for Indian English",
                type=eval_type,
                lan="en-in",
                granularity=1.0,
                num_eval=5,
                due_hours=12,
                auto_start=False,
                max_upload_workers=10,
            )
            self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_evaluation_list(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_evaluation_list()
        self.assertTrue(isinstance(response, list))  # type: ignore
        self.assertTrue(len(response) > 0)
        json = response[0]
        self.assertTrue("id" in json)
        self.assertTrue("title" in json)
        self.assertTrue("internal_name" in json)
        self.assertTrue("description" in json)
        self.assertTrue("status" in json)
        self.assertTrue("created_time" in json)
        self.assertTrue("updated_time" in json)

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_stimulus_stats_by_id(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_stats_json_by_id(evaluation_id=str(uuid4()))
        self.assertTrue(isinstance(response, list))  # type: ignore
        self.assertTrue(len(response) > 0)

        json = response[0]

        self.assertTrue("files" in json)
        self.assertTrue("question" in json)

        files = json["files"]
        self.assertTrue(isinstance(files, list))
        self.assertTrue(len(files) > 0)
        file = files[0]
        self.assertTrue("name" in file)
        self.assertTrue("model_tag" in file)
        self.assertTrue("tags" in file)
        self.assertTrue("type" in file)

        question = json["question"]
        self.assertTrue("title" in question)
        self.assertTrue("order" in question)

        optional_stats = ["mean", "median", "std"]
        for stat in optional_stats:
            if stat in json:
                self.assertTrue(isinstance(json[stat], (int, float)))

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_eval_template_info(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_eval_template_info(str(uuid4()))

        json = response

        self.assertTrue("id" in json)
        self.assertTrue("title" in json)
        self.assertTrue("description" in json)
        self.assertTrue("eval_type" in json)
        self.assertTrue(json["eval_type"] in ["Single", "Double", "Triple"])
        self.assertTrue("language" in json)
        self.assertTrue("created_time" in json)
        self.assertTrue("updated_time" in json)

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_single(self, mock_put: Any, mock_post: Any, mock_get: Any):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=True)

        # Mock successful responses
        resp = _make_response(json_data=[{"id": str(uuid4())} for _ in range(3)], status_code=200)
        mock_put.return_value = resp

        try:
            # When
            evaluator = self._mock_client.create_evaluator_from_template_json(
                json_file=json_path, name="Test Template Evaluation", custom_type="SINGLE", desc="Testing template-based evaluation", num_eval=5
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)  # type: ignore
            self.assertTrue(mock_put.call_count >= 2)

        finally:
            Path(json_path).unlink()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_double(self, mock_put: Any, mock_post: Any, mock_get: Any):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=False)

        # Mock successful responses
        resp = _make_response(json_data=[{"id": str(uuid4())} for _ in range(1)], status_code=200)
        mock_put.return_value = resp

        try:
            # When
            evaluator = self._mock_client.create_evaluator_from_template_json(
                json_file=json_path, name="Test Template Evaluation", custom_type="DOUBLE", desc="Testing template-based evaluation", num_eval=5
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.assertTrue(mock_put.call_count >= 1)

        finally:
            Path(json_path).unlink()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_create_evaluator_from_template_json_invalid_file(self, mock_post: Any, mock_get: Any):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        non_existent_path = "/path/to/nonexistent/file.json"

        # When/Then
        with self.assertRaises(FileNotFoundError):
            self._mock_client.create_evaluator_from_template_json(json_file=non_existent_path, name="Test Template Evaluation", custom_type="SINGLE")

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_create_evaluator_from_template_json_invalid_json(self, mock_post: Any, mock_get: Any):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"invalid": "json"')  # Invalid JSON structure
            json_path = f.name

        try:
            # When/Then
            with self.assertRaises(ValueError):
                self._mock_client.create_evaluator_from_template_json(json_file=json_path, name="Test Template Evaluation", custom_type="SINGLE")
        finally:
            # Cleanup
            Path(json_path).unlink()


class TestEvaluationClientApiKey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        api_key_envs = {"PODONOS_API_KEY": "ABCD123ENV"}
        cls.env = patch.dict(in_dict=os.environ, values=api_key_envs, clear=True)
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.env.stop()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_env_api_key_only(self, mock_get: Any):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init()
        self.assertTrue(isinstance(mock_client, Client))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_both_keys(self, mock_get: Any):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init(api_key="ABCD123PARAM")
        self.assertTrue(isinstance(mock_client, Client))  # type: ignore


class TestClient(unittest.TestCase):
    def setUp(self):
        self.valid_api_key = "test_key"
        # Use a real APIClient instance to satisfy strict type checks
        self.api_client = APIClient(self.valid_api_key, "http://testapi.com")
        self.client = Client(self.api_client)

        # Mock successful evaluation creation response
        self.mock_eval_response = {
            "id": str(uuid4()),
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "batch_size": 1,
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }

        self.template_data = {"questions": [{"type": "SCORED", "question": "Test Question", "options": [{"label_text": "Option 1"}]}]}

    def test_create_evaluator_from_json_dict_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data, name="Test Evaluation", custom_type="SINGLE", desc="Test Description"
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path, name="Test Evaluation", custom_type="SINGLE", desc="Test Description"
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.api_client.post.assert_called_once()
            self.assertTrue(self.api_client.put.call_count >= 1)

        finally:
            Path(template_path).unlink()

    def test_create_evaluator_with_both_json_inputs(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(json=self.template_data, json_file="test.json", name="Test", custom_type="SINGLE")
        self.assertIn("Only one of", str(context.exception))

    def test_create_evaluator_with_no_json_input(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(name="Test", custom_type="SINGLE")
        self.assertIn("Either 'json' or 'json_file' must be provided", str(context.exception))

    def test_create_evaluator_with_invalid_custom_type(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(json=self.template_data, name="Test", custom_type="TRIPLE")  # type: ignore
        self.assertIn('custom_type must be either "SINGLE" or "DOUBLE"', str(context.exception))

    def test_create_evaluator_from_json_dict_with_en_in_language(self):
        """Test creating evaluator from JSON dict with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data, name="Test EN-IN Evaluation", custom_type="SINGLE", desc="Test Description for Indian English"
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_with_en_in_language(self):
        """Test creating evaluator from JSON file with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path, name="Test EN-IN Evaluation", custom_type="SINGLE", desc="Test Description for Indian English"
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.api_client.post.assert_called_once()
            self.assertTrue(self.api_client.put.call_count >= 1)

        finally:
            Path(template_path).unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
