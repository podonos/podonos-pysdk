import os
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch, MagicMock


import podonos
from podonos.core.client import Client
from podonos.core.evaluator import Evaluator


def mocked_requests_post(*args, **kwargs):
    class MockResponse:
        def __init__(self, response_text, response_json, status_code):
            self.text = response_text
            self.json_response = response_json
            self.status_code = status_code

        def json(self):
            return self.json_response

        def raise_for_status(self):
            return

    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = dict(
            id="mock_id",
            title="mock_title",
            internal_name="mock_internal_name",
            batch_size=1,
            description="mock_desc",
            status="mock_status",
            created_time="2024-05-21T06:18:09.659270Z",
            updated_time="2024-05-21T06:18:09.659270Z",
        )
        return MockResponse(None, evaluation_list, 200)

    return MockResponse(None, None, 404)


# Mocks HTTP GET request.
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, response_text, response_json, status_code):
            self.text = response_text
            self.json_response = response_json
            self.status_code = status_code

        def json(self):
            return self.json_response

        def raise_for_status(self):
            return

    if "/customers/verify/api-key" in args[0]:
        # API key verification
        return MockResponse("true", None, 200)

    if "/version/sdk" in args[0]:
        # SDK versions
        version_response = dict(latest="0.1.5", recommended="0.1.4", minimum="0.1.0")
        return MockResponse(None, version_response, 200)

    if "/evaluations" in args[0] and "/stats" in args[0]:
        # Stats by id
        evaluation_stats = [
            dict(
                files=[{"name": "tr16.wav", "model_tag": "my_model", "tags": ["generated"], "type": "A"}],
                question={
                    "title": "Attending **ONLY to the BACKGROUND (noise or other speakers' voices)**, select the category which best describes the sample you just heard.",
                    "order": 0,
                },
                mean=3.4,
                median=3.5,
                std=1.07,
                option_a=True,
                option_b=False,
            )
        ]
        return MockResponse(None, evaluation_stats, 200)

    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = [
            dict(
                id="mock_id",
                title="mock_title",
                internal_name="mock_internal_name",
                description="mock_desc",
                batch_size=1,
                status="mock_status",
                created_time="2024-05-21T06:18:09.659270Z",
                updated_time="2024-05-21T06:18:09.659270Z",
            )
        ]
        return MockResponse(None, evaluation_list, 200)

    return MockResponse(None, None, 404)


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
    def test_single_stimulus_evaluator_creation(self, mock_get, mock_post):
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
        self.assertTrue(isinstance(etor, Evaluator))

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_double_stimuli_evaluator_creation(self, mock_get, mock_post):
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
        self.assertTrue(isinstance(etor, Evaluator))

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_evaluation_list(self, mock_get):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_evaluation_list()
        self.assertTrue(isinstance(response, list))
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
    def test_stimulus_stats_by_id(self, mock_get):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_stats_dict_by_id(evaluation_id="mock_id")
        self.assertTrue(isinstance(response, list))
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
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_single(self, mock_put, mock_post, mock_get):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=True)

        # Mock successful responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": f"question_{i}"} for i in range(3)]
        mock_put.return_value = mock_response

        try:
            # When
            evaluator = self._mock_client.create_evaluator_from_template_json(
                json_file=json_path, name="Test Template Evaluation", custom_type="SINGLE", desc="Testing template-based evaluation", num_eval=5
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.assertTrue(mock_put.call_count >= 2)

        finally:
            Path(json_path).unlink()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_double(self, mock_put, mock_post, mock_get):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=False)

        # Mock successful responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": f"question_{i}"} for i in range(1)]
        mock_put.return_value = mock_response

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
    def test_create_evaluator_from_template_json_invalid_file(self, mock_post, mock_get):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        non_existent_path = "/path/to/nonexistent/file.json"

        # When/Then
        with self.assertRaises(FileNotFoundError):
            self._mock_client.create_evaluator_from_template_json(json_file=non_existent_path, name="Test Template Evaluation", custom_type="SINGLE")

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_create_evaluator_from_template_json_invalid_json(self, mock_post, mock_get):
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
    def test_env_api_key_only(self, mock_get):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init()
        self.assertTrue(isinstance(mock_client, Client))

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_both_keys(self, mock_get):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init(api_key="ABCD123PARAM")
        self.assertTrue(isinstance(mock_client, Client))


class TestClient(unittest.TestCase):
    def setUp(self):
        self.valid_api_key = "test_key"
        self.api_client = MagicMock()
        self.client = Client(self.api_client)

        # Mock successful evaluation creation response
        self.mock_eval_response = {
            "id": "mock_id",
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "batch_size": 1,
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-03-21T06:18:09.659270Z",
            "updated_time": "2024-03-21T06:18:09.659270Z",
        }

        self.template_data = {"questions": [{"type": "SCORED", "question": "Test Question", "options": [{"label_text": "Option 1"}]}]}

    def test_create_evaluator_from_json_dict_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        self.api_client.post.return_value = mock_post_response

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": "question_1"}]
        self.api_client.put.return_value = mock_put_response

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
        self.api_client.post.return_value = mock_post_response

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": "question_1"}]
        self.api_client.put.return_value = mock_put_response

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
