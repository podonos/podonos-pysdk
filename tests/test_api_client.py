import re
import unittest
from unittest.mock import patch, MagicMock
from podonos.core.api import APIClient, APIVersion


class TestAPIVersion(unittest.TestCase):
    def teatVersions(self):
        minimum = "0.1.0"
        recommended = "0.1.5"
        latest = "0.2.0"
        ver = APIVersion(minimum, recommended, latest)
        self.assertEqual(minimum, ver.minimum)
        self.assertEqual(recommended, ver.recommended)
        self.assertEqual(latest, ver.latest)


class TestAPIClient(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_api_key"
        self.api_url = "http://testapi.com"
        self.client = APIClient(self.api_key, self.api_url)

    def test_params(self):
        self.assertEqual(self.api_key, self.client.api_key)
        self.assertEqual(self.api_url, self.client.api_url)

    @patch("requests.get")
    def test_get_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "true"
        mock_get.return_value = mock_response

        response = self.client.get("test-endpoint")
        self.assertEqual(response.text, "true")
        mock_get.assert_called_once_with(f"{self.api_url}/test-endpoint", headers=self.client._headers, params=None)

    @patch("requests.post")
    def test_post_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        data = {"key": "value"}
        response = self.client.post("test-endpoint", data)
        self.assertEqual(response.status_code, 200)
        mock_post.assert_called_once_with(f"{self.api_url}/test-endpoint", headers=self.client._headers, json=data)

    @patch("requests.put")
    def test_put_success(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        data = {"key": "value"}
        response = self.client.put("test-endpoint", data)
        self.assertEqual(response.status_code, 200)
        mock_put.assert_called_once_with(f"{self.api_url}/test-endpoint", headers=self.client._headers, json=data)

    @patch("podonos.core.api.APIClient._check_minimum_version")
    @patch("podonos.core.api.APIClient.get")
    def test_initialize_success(self, mock_get, mock_check_minimum_version):
        mock_response = MagicMock()
        mock_response.text = "true"
        mock_get.return_value = mock_response
        mock_check_minimum_version.return_value = True

        result = self.client.initialize()
        self.assertTrue(result)
        mock_get.assert_called_once_with(f"customers/verify/api-key")

    @patch("podonos.core.api.APIClient._check_minimum_version")
    @patch("podonos.core.api.APIClient.get")
    def test_initialize_invalid_api_key(self, mock_get, mock_check_minimum_version):
        mock_response = MagicMock()
        mock_response.text = "false"
        mock_get.return_value = mock_response
        mock_check_minimum_version.return_value = True

        with self.assertRaises(ValueError) as context:
            self.client.initialize()

        self.assertIn("Invalid API key", str(context.exception))
        mock_get.assert_called_once_with("customers/verify/api-key")

    def test_add_headers(self):
        self.client.add_headers("New-Header", "HeaderValue")
        self.assertIn("New-Header", self.client._headers)
        self.assertEqual(self.client._headers["New-Header"], "HeaderValue")

    @patch("importlib.metadata.version")
    def test_get_podonos_version_success(self, mock_version):
        mock_version.return_value = "1.2.3"

        result = self.client._get_podonos_version()
        self.assertEqual(result, "1.2.3")
        mock_version.assert_called_once_with("podonos")

    def test_get_content_type(self):
        path_wav = '/a/b/123.wav'
        self.assertEqual("audio/wav", self.client._get_content_type_by_filename(path_wav))

        path_wav = '/a/b/456.mp3'
        self.assertEqual("audio/mpeg", self.client._get_content_type_by_filename(path_wav))

        path_wav = '/a/b/789.json'
        self.assertEqual("application/json", self.client._get_content_type_by_filename(path_wav))

        path_wav = '/a/b/abc.obj'
        self.assertEqual("application/octet-stream", self.client._get_content_type_by_filename(path_wav))

    def test_package_version(self):
        version_str = self.client._get_podonos_version()
        # Test the version string is in the format of "<decimal_version>.<decimal_subversion>"
        self.assertTrue(re.search(r'\d+\.\d+', version_str))


if __name__ == "__main__":
    unittest.main()
