import podonos
import unittest
from unittest import mock


# Mocks HTTP GET request.
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, response_text, response_json, status_code):
            self.text_response = response_text
            self.json_response = response_json
            self.status_code = status_code

        def json(self):
            return self.json_response

    if '/clients/verify' in args[0]:
        # API key verification
        return MockResponse('true', None, 200)

    if '/version/sdk' in args[0]:
        # SDK versions
        version_response = dict(
            latest="0.1.0",
            recommended="0.0.12",
            minimum="0.0.12")
        return MockResponse(None,
                            version_response,
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
        self.assertTrue(isinstance(valid_client, podonos.EvalClient))


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
    def test_create_evaluator(self, mock_get):
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


if __name__ == '__main__':
    unittest.main()
