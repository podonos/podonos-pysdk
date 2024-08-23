import unittest
from podonos.core.config import EvalConfig


class TestEvalConfig(unittest.TestCase):
    def setUp(self):
        self.eval_config = EvalConfig()

    def test_set_eval_use_annotation_valid_types(self):
        valid_eval_types = ["NMOS", "QMOS", "P808"]

        for eval_type in valid_eval_types:
            result = self.eval_config._validate_eval_use_annotation(eval_use_annotation=True, eval_type=eval_type)
            self.assertTrue(result)

    def test_set_eval_use_annotation_invalid_type(self):
        invalid_eval_type = "SMOS"

        with self.assertRaises(ValueError) as context:
            self.eval_config._validate_eval_use_annotation(eval_use_annotation=True, eval_type=invalid_eval_type)

        self.assertEqual(str(context.exception), '"eval_type" must be one of {NMOS, QMOS, P808} when using "use_annotation"')
