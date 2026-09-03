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
        # The progress fields are absent from valid_data, so they round-trip as None rather
        # than vanishing. Every key the caller had before is still present and unrenamed.
        expected = dict(self.valid_data)
        expected.update(
            progress=None, internal_status=None, started_time=None, ended_time=None
        )
        self.assertEqual(result, expected)

    def test_from_dict_reads_progress_fields_when_present(self):
        # Given
        data = dict(self.valid_data)
        data.update(
            progress=52.5,
            internal_status="EVAL_HUMAN_EVAL_START",
            started_time="2023-10-01T13:00:00.000Z",
            ended_time="2023-10-03T13:00:00.000Z",
        )

        # When
        entity = EvaluationEntity.from_dict(data)

        # Then
        self.assertEqual(entity.progress, 52.5)
        self.assertEqual(entity.internal_status, "EVAL_HUMAN_EVAL_START")
        self.assertEqual(
            entity.started_time, datetime.fromisoformat("2023-10-01T13:00:00.000+00:00")
        )
        self.assertEqual(
            entity.ended_time, datetime.fromisoformat("2023-10-03T13:00:00.000+00:00")
        )
        self.assertEqual(entity.to_dict()["started_time"], "2023-10-01T13:00:00.000Z")

    def test_from_dict_accepts_null_started_and_ended_time(self):
        # Given
        # A DRAFT evaluation really does send null for both, which is why the parse cannot be
        # unconditional the way created_time's is.
        data = dict(self.valid_data)
        data.update(progress=0.0, internal_status="EVAL_STAGE", started_time=None, ended_time=None)

        # When
        entity = EvaluationEntity.from_dict(data)

        # Then
        self.assertIsNone(entity.started_time)
        self.assertIsNone(entity.ended_time)
        self.assertEqual(entity.progress, 0.0)


if __name__ == "__main__":
    unittest.main()
