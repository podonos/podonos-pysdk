import os
import unittest
import requests
from unittest.mock import Mock, patch, MagicMock
from typing import Optional

from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import File

class MockEvaluator(Evaluator):
    def __init__(self, api_client = Mock(spec=APIClient), eval_config: Optional[EvalConfig] = None):
        super().__init__(api_client, eval_config)

    def add_file(self, file: File) -> None:
        pass
    
    def add_file_pair(self, target: File, ref: File) -> None:
        pass
    
    def add_file_set(self, file0: File, file1: File) -> None:
        pass
    
class TestEvaluator(unittest.TestCase):
    
    def setUp(self):
        self.eval_config = EvalConfig(type='NMOS')
        self.evaluator = MockEvaluator(eval_config=self.eval_config)

    def test_get_eval_config_success(self):
        eval_config = EvalConfig(type='NMOS')
        evaluator = MockEvaluator(eval_config=eval_config)
        
        result = evaluator._get_eval_config()
        self.assertEqual(result, eval_config)

    def test_get_eval_config_not_initialized(self):
        evaluator = MockEvaluator(eval_config=None)
        
        with self.assertRaises(ValueError) as context:
            evaluator._get_eval_config()
        
        self.assertEqual(str(context.exception), "Evaluator is not initialized")

    def test_post_request_evaluation_success(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = MagicMock(status_code=200)
        
        eval_config = EvalConfig("NMOS")
        evaluator = MockEvaluator(eval_config=eval_config)
        evaluator._api_client.post.return_value = mock_response # type: ignore
        
        evaluator._post_request_evaluation()
        evaluator._api_client.post.assert_called_once_with("request-evaluation", { # type: ignore
            'eval_id': eval_config.eval_id,
            'eval_type': 'SPEECH_NMOS'
        })

    def test_post_request_evaluation_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=MagicMock(status_code=400))
        mock_api_client = MagicMock()
        evaluator = MockEvaluator(api_client=mock_api_client, eval_config=EvalConfig("NMOS"))
        evaluator._api_client.post.return_value = mock_response # type: ignore

        with self.assertRaises(HTTPError):
            evaluator._post_request_evaluation()

    @patch('os.path.isfile')
    @patch('os.access')
    def test_validate_path_success(self, mock_access, mock_isfile):
        mock_isfile.return_value = True
        mock_access.return_value = True

        evaluator = MockEvaluator(eval_config=EvalConfig(type='NMOS'))
        
        valid_path = '/valid/path/to/file.txt'
        result = evaluator._validate_path(valid_path)
        self.assertEqual(result, valid_path)
        
        mock_isfile.assert_called_once_with(valid_path)
        mock_access.assert_called_once_with(valid_path, os.R_OK)

    @patch('os.path.isfile')
    @patch('os.access')
    def test_validate_path_file_not_exist(self, mock_access, mock_isfile):
        mock_isfile.return_value = False
        evaluator = MockEvaluator(eval_config=EvalConfig(type='NMOS'))
        
        invalid_path = '/invalid/path/to/file.txt'
        with self.assertRaises(FileNotFoundError) as context:
            evaluator._validate_path(invalid_path)
        
        self.assertIn("doesn't exist", str(context.exception))
        
        mock_isfile.assert_called_once_with(invalid_path)
        mock_access.assert_not_called()

    @patch('os.path.isfile')
    @patch('os.access')
    def test_validate_path_not_readable(self, mock_access, mock_isfile):
        mock_isfile.return_value = True
        mock_access.return_value = False

        evaluator = MockEvaluator(eval_config=EvalConfig(type='NMOS'))
        
        unreadable_path = '/unreadable/path/to/file.txt'
        with self.assertRaises(FileNotFoundError) as context:
            evaluator._validate_path(unreadable_path)
        
        self.assertIn("isn't readable", str(context.exception))
        
        mock_isfile.assert_called_once_with(unreadable_path)
        mock_access.assert_called_once_with(unreadable_path, os.R_OK)

if __name__ == '__main__':
    unittest.main()
