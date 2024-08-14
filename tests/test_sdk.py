import os
import podonos
import unittest
from unittest import mock

from podonos.core.file import File
from podonos.common.constant import *


# Mocks HTTP GET request.
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, response_text, response_json, status_code):
            self.text = response_text
            self.json_response = response_json
            self.status_code = status_code

        def json(self):
            return self.json_response

    if '/customers/verify/api-key' in args[0]:
        # API key verification
        return MockResponse('true', None, 200)

    if '/version/sdk' in args[0]:
        # SDK versions
        version_response = dict(
            latest="0.1.5",
            recommended="0.1.4",
            minimum="0.1.0")
        return MockResponse(None,
                            version_response,
                            200)

    if '/customers/uploading-presigned-url' in args[0]:
        return MockResponse("https://fake.podonos.com/my_url1", None, 200)

    return MockResponse(None, None, 404)


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

    if '/evaluations' in args[0]:
        # evaluations
        evaluation_response = dict(
            id="mock_id",
            title="mock_title",
            internal_name="mock_internal_name",
            description="mock_desc",
            status="mock_status",
            created_time="2024-05-21T06:18:09.659270Z",
            updated_time="2024-05-22T06:18:09.659270Z"
        )
        return MockResponse(None,
                            evaluation_response,
                            200)

    return MockResponse(None, None, 404)


class TestPodonos(unittest.TestCase):

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_init(self, mock_get):
        # Invalid api_key
        invalid_api_key = '1'
        with self.assertRaises(Exception) as context:
            _ = podonos.init(invalid_api_key)

        # Valid api_key
        valid_api_key = '12345678'
        valid_client = podonos.init(valid_api_key)
        self.assertTrue(isinstance(valid_client, podonos.Client))

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_init_api_key_env(self, mock_get):
        # Valid api_key_env
        os.environ[PODONOS_API_KEY] = "ABCDEFG"
        valid_client = podonos.init()
        self.assertTrue(isinstance(valid_client, podonos.Client))

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_init_both_api_keys(self, mock_get):
        # Valid api_key_env
        os.environ[PODONOS_API_KEY] = "ABCDEFG"
        valid_api_key = '12345678'
        valid_client = podonos.init(valid_api_key)
        self.assertTrue(isinstance(valid_client, podonos.Client))


class TestPodonosClient(unittest.TestCase):

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def setUp(self, mock_get) -> None:
        valid_api_key = "1234567890"
        self._mock_client = podonos.init(api_key=valid_api_key)

        self.config = {
            'name': 'my_new_model_03272024_p1_k2_en_us',
            'desc': 'Updated model',
            'type': 'NMOS',
            'lan': 'en-us'
        }

    @mock.patch('requests.get', side_effect=mocked_requests_get)
    @mock.patch('requests.post', side_effect=mocked_requests_post)
    def test_create_evaluator(self, mock_get, mock_post):
        # Missing name is allowed.
        etor = self._mock_client.create_evaluator(
            desc=self.config['desc'],
            type=self.config['type'],
            lan=self.config['lan'])
        self.assertIsNotNone(etor)

        # Too short name.
        with self.assertRaises(ValueError) as context:
            _ = self._mock_client.create_evaluator(
                name='a',
                desc=self.config['desc'],
                type=self.config['type'],
                lan=self.config['lan'])

        # Missing description is allowed.
        etor = self._mock_client.create_evaluator(
            name=self.config['name'],
            type=self.config['type'],
            lan=self.config['lan'])
        self.assertIsNotNone(etor)

        # Unknown type.
        with self.assertRaises(ValueError) as context:
            _ = self._mock_client.create_evaluator(
                name=self.config['name'],
                desc=self.config['desc'],
                type="unknown_type",
                lan=self.config['lan'])

        # Missing language is allowed.
        etor = self._mock_client.create_evaluator(
            name=self.config['name'],
            desc=self.config['desc'],
            type=self.config['type'])
        self.assertIsNotNone(etor)

        # Invalid language.
        with self.assertRaises(ValueError) as context:
            _ = self._mock_client.create_evaluator(
                name=self.config['name'],
                desc=self.config['desc'],
                type=self.config['type'],
                lan='abcd')

        # Valid configuration
        etor = self._mock_client.create_evaluator(
            name=self.config['name'],
            desc=self.config['desc'],
            type=self.config['type'],
            lan=self.config['lan'])
        self.assertIsNotNone(etor)

        # P.808
        etor = self._mock_client.create_evaluator(
            name=self.config['name'],
            desc=self.config['desc'],
            type='P808',
            lan=self.config['lan'])
        self.assertIsNotNone(etor)

        # SMOS
        etor = self._mock_client.create_evaluator(
            name=self.config['name'],
            desc=self.config['desc'],
            type='SMOS',
            lan=self.config['lan'])
        self.assertIsNotNone(etor)


class TestPodonosEvaluator(unittest.TestCase):

    @unittest.skip
    @mock.patch('requests.get', side_effect=mocked_requests_get)
    def test_evaluator(self, mock_get):
        valid_api_key = "1234567890"
        self._mock_client = podonos.init(api_key=valid_api_key)

        self.config = {
            'name': 'my_new_model_03272024_p1_k2_en_us',
            'desc': 'Updated model',
            'type': 'NMOS',
            'lan': 'en-us'
        }

        etor = self._mock_client.create_evaluator(
            name='new_model', desc='', type='NMOS', lan='en-au')
        self.assertIsNotNone(etor)

        some_file = os.path.join(os.path.dirname(__file__), '../speech_0_0.mp3')
        etor.add_file(File(path=some_file, tags=['unknown_file,new_model']))
        etor.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
