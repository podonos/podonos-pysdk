import unittest
from datetime import datetime
from podonos.entity.evaluation import EvaluationEntity


class TestEvaluationEntity(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "id": "123",
            "title": "Test Evaluation",
            "internal_name": "test_eval",
            "description": "This is a test evaluation.",
            "batch_size": 10,
            "status": "active",
            "created_time": "2023-10-01T12:00:00.000Z",
            "updated_time": "2023-10-02T12:00:00.000Z",
        }

    def test_from_dict_success(self):
        # When
        entity = EvaluationEntity.from_dict(self.valid_data)

        # Then
        self.assertEqual(entity.id, self.valid_data["id"])
        self.assertEqual(entity.title, self.valid_data["title"])
        self.assertEqual(entity.internal_name, self.valid_data["internal_name"])
        self.assertEqual(entity.description, self.valid_data["description"])
        self.assertEqual(entity.batch_size, self.valid_data["batch_size"])
        self.assertEqual(entity.status, self.valid_data["status"])
        self.assertEqual(entity.created_time, datetime.fromisoformat(self.valid_data["created_time"].replace("Z", "+00:00")))
        self.assertEqual(entity.updated_time, datetime.fromisoformat(self.valid_data["updated_time"].replace("Z", "+00:00")))

    def test_from_dict_missing_key(self):
        # Given
        invalid_data = self.valid_data.copy()
        del invalid_data["id"]

        # When/Then
        with self.assertRaises(ValueError) as context:
            EvaluationEntity.from_dict(invalid_data)
        self.assertIn("Invalid data format for Evaluation", str(context.exception))

    def test_to_dict(self):
        # Given
        entity = EvaluationEntity.from_dict(self.valid_data)

        # When
        result = entity.to_dict()

        # Then
        self.assertEqual(result, self.valid_data)


if __name__ == "__main__":
    unittest.main()
