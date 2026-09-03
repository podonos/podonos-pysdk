import unittest
from datetime import datetime, timedelta, timezone
from podonos.entity.evaluation import EvaluationEntity, EvaluationProgress


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


class TestEvaluationProgress(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "id": "123",
            "status": "ACTIVE",
            "internal_status": "EVAL_HUMAN_EVAL_START",
            "progress": 52.5,
            "started_time": "2026-09-03T04:10:22.123456",
            "ended_time": None,
        }

    def test_from_dict_success(self):
        # When
        progress = EvaluationProgress.from_dict(self.valid_data)

        # Then
        self.assertEqual(progress.id, "123")
        self.assertEqual(progress.status, "ACTIVE")
        self.assertEqual(progress.internal_status, "EVAL_HUMAN_EVAL_START")
        self.assertEqual(progress.progress, 52.5)
        self.assertEqual(
            progress.started_time, datetime.fromisoformat("2026-09-03T04:10:22.123456+00:00")
        )
        self.assertIsNone(progress.ended_time)

    def test_naive_and_zulu_timestamps_both_parse_aware_utc(self):
        # The backend sends created_time with a "Z" and started_time with no offset. Both must
        # come out aware, or subtracting one from the other raises TypeError.
        progress = EvaluationProgress.from_dict(self.valid_data)
        entity = EvaluationEntity.from_dict(
            {
                "id": "1", "title": "t", "internal_name": None, "description": None,
                "batch_size": 1, "status": "ACTIVE",
                "created_time": "2026-09-03T04:00:00.000Z",
                "updated_time": "2026-09-03T04:00:00.000Z",
            }
        )

        self.assertEqual(progress.started_time.tzinfo, timezone.utc)
        self.assertEqual(entity.created_time.tzinfo, timezone.utc)
        self.assertEqual(
            progress.started_time - entity.created_time, timedelta(minutes=10, seconds=22, microseconds=123456)
        )

    def test_a_malformed_optional_time_degrades_to_none(self):
        # Optional fields must not take a whole evaluation list down. A bad started_time on
        # one row is one missing field, not a failed get_evaluation_list().
        data = dict(self.valid_data)
        data["started_time"] = 1716272289

        progress = EvaluationProgress.from_dict(data)

        self.assertIsNone(progress.started_time)
        self.assertEqual(progress.progress, 52.5)

    def test_to_dict_converts_a_non_utc_offset_before_labelling_it_z(self):
        # A "+09:00" input must not be re-emitted with its wall clock and a "Z" suffix, which
        # would silently move it nine hours.
        data = dict(self.valid_data)
        data["started_time"] = "2026-09-03T13:10:22.123+09:00"

        progress = EvaluationProgress.from_dict(data)

        self.assertEqual(progress.to_dict()["started_time"], "2026-09-03T04:10:22.123Z")

    def test_from_dict_missing_key(self):
        # Given
        invalid_data = self.valid_data.copy()
        del invalid_data["progress"]

        # When/Then
        with self.assertRaises(ValueError) as context:
            EvaluationProgress.from_dict(invalid_data)
        self.assertIn("Invalid data format for EvaluationProgress", str(context.exception))

    def test_evaluation_entity_cannot_parse_a_progress_payload(self):
        # The two payloads share four field names but not a type. Pointing the entity at a
        # progress response is the mistake this separate class exists to prevent.
        with self.assertRaises(ValueError):
            EvaluationEntity.from_dict(self.valid_data)


if __name__ == "__main__":
    unittest.main()
