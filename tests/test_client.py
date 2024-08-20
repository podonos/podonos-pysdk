import os
import podonos
from podonos.core.client import Client

import unittest
from unittest import mock
from unittest.mock import patch


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
            dict(files=[{"name": "tr16.wav", "tags": ["generated"], "type": "A"}], mean=3.4, median=3.5, std=1.07, ci_90=1.14, ci_95=1.48, ci_99=1.53)
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
                status="mock_status",
                created_time="2024-05-21T06:18:09.659270Z",
                updated_time="2024-05-21T06:18:09.659270Z",
            )
        ]
        return MockResponse(None, evaluation_list, 200)

    return MockResponse(None, None, 404)


class TestEvaluationClient(unittest.TestCase):

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_evaluation_list(self, mock_get):
        valid_api_key = "1234567890"
        self._mock_client = podonos.init(api_key=valid_api_key)
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
        valid_api_key = "1234567890"
        self._mock_client = podonos.init(api_key=valid_api_key)
        response = self._mock_client.get_stats_dict_by_id(evaluation_id="mock_id")
        self.assertTrue(isinstance(response, list))
        self.assertTrue(len(response) > 0)
        json = response[0]
        self.assertTrue("files" in json)
        self.assertTrue("mean" in json)
        self.assertTrue("median" in json)
        self.assertTrue("std" in json)
        self.assertTrue("ci_90" in json)
        self.assertTrue("ci_95" in json)
        self.assertTrue("ci_99" in json)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
