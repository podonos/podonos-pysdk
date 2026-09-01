import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from requests import Response

import podonos
from podonos.common.enum import EvalType, QuestionFileType
from podonos.common.util import calculate_file_md5_base64
from podonos.core.api import APIClient
from podonos.core.client import Client
from podonos.core.evaluator import Evaluator
from podonos.core.file import Audio, File
from podonos.core.upload_ledger import UploadLedger, build_upload_manifest_hash


def _make_response(
    text: Any = None, json_data: Any = None, status_code: int = 200
) -> Response:
    resp = Response()
    resp.status_code = status_code
    if json_data is not None:
        resp._content = json.dumps(json_data).encode("utf-8")
        resp.headers["Content-Type"] = "application/json"
    elif text is not None:
        resp._content = str(text).encode("utf-8")
    else:
        resp._content = b""
    return resp


def _resume_contract(
    evaluation_id: str,
    *,
    eval_type: str = "NMOS",
    eval_batch_size: int = 1,
    eval_template_id: str | None = None,
    use_annotation: bool = False,
    use_loudness_normalization: bool = True,
    session_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_config: dict[str, Any] = {
        "eval_name": "original-evaluation",
        "eval_description": "original description",
        "eval_type": eval_type,
        "eval_language": "en-us",
        "eval_num": 10,
        "eval_expected_due": "2026-05-22T00:00:00.000+00:00",
        "eval_creation_timestamp": "2026-05-21T00:00:00.000",
        "eval_use_annotation": use_annotation,
        "eval_auto_start": False,
        "eval_template_id": eval_template_id,
        "use_loudness_normalization": use_loudness_normalization,
        "max_upload_workers": 20,
        "verify_batch_size": 100,
    }
    if session_overrides:
        session_config.update(session_overrides)
    return {
        "evaluation_id": evaluation_id,
        "eval_type": eval_type,
        "eval_language": "en-us",
        "eval_batch_size": eval_batch_size,
        "eval_template_id": eval_template_id,
        "use_annotation": use_annotation,
        "use_loudness_normalization": use_loudness_normalization,
        "session_config": session_config,
    }


def mocked_requests_post(*args: Any, **kwargs: Any):
    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = dict(
            id=str(uuid4()),
            title="mock_title",
            internal_name="mock_internal_name",
            batch_size=1,
            description="mock_desc",
            status="mock_status",
            created_time="2024-05-21T06:18:09.659Z",
            updated_time="2024-05-21T06:18:09.659Z",
        )
        return _make_response(json_data=evaluation_list, status_code=200)

    return _make_response(status_code=404)


# Mocks HTTP GET request.
def mocked_requests_get(*args: Any, **kwargs: Any):
    if "/customers/verify/api-key" in args[0]:
        # API key verification
        return _make_response(text="true", status_code=200)

    if "/version/sdk" in args[0]:
        # SDK versions
        version_response = dict(latest="0.1.5", recommended="0.1.4", minimum="0.1.0")
        return _make_response(json_data=version_response, status_code=200)

    if "/evaluations" in args[0] and "/stats" in args[0]:
        # Stats by id
        evaluation_stats = [
            dict(
                files=[
                    {
                        "name": "tr16.wav",
                        "model_tag": "my_model",
                        "tags": ["generated"],
                        "type": "A",
                    }
                ],
                question={
                    "title": "Attending **ONLY to the BACKGROUND (noise or other speakers' voices)**, "
                    "select the category which best describes the sample you just heard.",
                    "order": 0,
                },
                mean=3.4,
                median=3.5,
                std=1.07,
                option_a=True,
                option_b=False,
            )
        ]
        return _make_response(json_data=evaluation_stats, status_code=200)

    if "/evaluations" in args[0]:
        # Evaluation list
        evaluation_list = [
            dict(
                id=str(uuid4()),
                title="mock_title",
                internal_name="mock_internal_name",
                description="mock_desc",
                batch_size=1,
                status="mock_status",
                created_time="2024-05-21T06:18:09.659Z",
                updated_time="2024-05-21T06:18:09.659Z",
            )
        ]
        return _make_response(json_data=evaluation_list, status_code=200)

    if "/templates" in args[0]:
        eval_template_info = dict(
            id=str(uuid4()),
            code="mock_code",
            title="mock_title",
            description="mock_description",
            eval_type="CUSTOM",
            batch_size=1,
            use_annotation=False,
            use_power_normalization=True,
            language="en-us",
            created_time="2025-05-21T06:18:09.659Z",
            updated_time="2025-05-28T13:59:12.123Z",
        )
        return _make_response(json_data=eval_template_info, status_code=200)

    return _make_response(status_code=404)


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
                    "options": [
                        {"label_text": "Background Noise"},
                        {"label_text": "Echo"},
                        {"label_text": "Distortion"},
                    ],
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
                    "anchor_label": {
                        "title": "Preference",
                        "label_text": {"left": "Better", "right": "Better"},
                    },
                }
            ]
        }

    def create_temp_json_file(self, is_single: bool = True) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                self.single_template_json if is_single else self.double_template_json, f
            )
            return f.name

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_single_stimulus_evaluator_creation(self, mock_get: Any, mock_post: Any):
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
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_double_stimuli_evaluator_creation(self, mock_get: Any, mock_post: Any):
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
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_single_stimulus_evaluator_creation_with_en_in_language(
        self, mock_get: Any, mock_post: Any
    ):
        """Test single stimulus evaluator creation with en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "en_in_test"
        desc = "detailed description for Indian English"
        type = "NMOS"
        lan = "en-in"  # Indian English
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
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_double_stimuli_evaluator_creation_with_en_in_language(
        self, mock_get: Any, mock_post: Any
    ):
        """Test double stimuli evaluator creation with en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        name = "en_in_double_test"
        desc = "detailed description for Indian English double stimuli"
        type = "PREF"
        lan = "en-in"  # Indian English
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
        self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_evaluator_creation_with_all_eval_types_en_in_language(
        self, mock_get: Any, mock_post: Any
    ):
        """Test evaluator creation with all evaluation types using en-in language"""
        self._mock_client = podonos.init(api_key=self.valid_api_key)

        # Test all evaluation types with en-in language
        eval_types = [
            "NMOS",
            "QMOS",
            "SMOS",
            "P808",
            "PREF",
            "CSMOS",
            "CUSTOM_SINGLE",
            "CUSTOM_DOUBLE",
        ]

        for eval_type in eval_types:
            etor = self._mock_client.create_evaluator(
                name=f"en_in_{eval_type.lower()}_test",
                desc=f"Test {eval_type} evaluation for Indian English",
                type=eval_type,
                lan="en-in",
                granularity=1.0,
                num_eval=5,
                due_hours=12,
                auto_start=False,
                max_upload_workers=10,
            )
            self.assertTrue(isinstance(etor, Evaluator))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_evaluation_list(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_evaluation_list()
        self.assertTrue(isinstance(response, list))  # type: ignore
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
    def test_stimulus_stats_by_id(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_stats_json_by_id(evaluation_id=str(uuid4()))
        self.assertTrue(isinstance(response, list))  # type: ignore
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
    def test_eval_template_info(self, mock_get: Any):
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        response = self._mock_client.get_eval_template_info(str(uuid4()))

        json = response

        self.assertTrue("id" in json)
        self.assertTrue("title" in json)
        self.assertTrue("description" in json)
        self.assertTrue("eval_type" in json)
        self.assertTrue(json["eval_type"] in ["Single", "Double", "Triple"])
        self.assertTrue("language" in json)
        self.assertTrue("created_time" in json)
        self.assertTrue("updated_time" in json)

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_single(
        self, mock_put: Any, mock_post: Any, mock_get: Any
    ):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=True)

        # Mock successful responses
        resp = _make_response(
            json_data=[{"id": str(uuid4())} for _ in range(3)], status_code=200
        )
        mock_put.return_value = resp

        try:
            # When
            evaluator = self._mock_client.create_evaluator_from_template_json(
                json_file=json_path,
                name="Test Template Evaluation",
                custom_type="SINGLE",
                desc="Testing template-based evaluation",
                num_eval=5,
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)  # type: ignore
            self.assertTrue(mock_put.call_count >= 2)

        finally:
            Path(json_path).unlink()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    @mock.patch("requests.put")
    def test_create_evaluator_from_template_json_double(
        self, mock_put: Any, mock_post: Any, mock_get: Any
    ):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        json_path = self.create_temp_json_file(is_single=False)

        # Mock successful responses
        resp = _make_response(
            json_data=[{"id": str(uuid4())} for _ in range(1)], status_code=200
        )
        mock_put.return_value = resp

        try:
            # When
            evaluator = self._mock_client.create_evaluator_from_template_json(
                json_file=json_path,
                name="Test Template Evaluation",
                custom_type="DOUBLE",
                desc="Testing template-based evaluation",
                num_eval=5,
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.assertTrue(mock_put.call_count >= 1)

        finally:
            Path(json_path).unlink()

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_create_evaluator_from_template_json_invalid_file(
        self, mock_post: Any, mock_get: Any
    ):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        non_existent_path = "/path/to/nonexistent/file.json"

        # When/Then
        with self.assertRaises(FileNotFoundError):
            self._mock_client.create_evaluator_from_template_json(
                json_file=non_existent_path,
                name="Test Template Evaluation",
                custom_type="SINGLE",
            )

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    @mock.patch("requests.post", side_effect=mocked_requests_post)
    def test_create_evaluator_from_template_json_invalid_json(
        self, mock_post: Any, mock_get: Any
    ):
        # Given
        self._mock_client = podonos.init(api_key=self.valid_api_key)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"invalid": "json"')  # Invalid JSON structure
            json_path = f.name

        try:
            # When/Then
            with self.assertRaises(ValueError):
                self._mock_client.create_evaluator_from_template_json(
                    json_file=json_path,
                    name="Test Template Evaluation",
                    custom_type="SINGLE",
                )
        finally:
            # Cleanup
            Path(json_path).unlink()


class TestClientFromTemplateJson(unittest.TestCase):
    def setUp(self):
        self.valid_api_key = "test_key"
        # Use a real APIClient instance to satisfy strict type checks
        self.api_client = APIClient(self.valid_api_key, "http://testapi.com")
        self.client = Client(self.api_client)

        # Mock successful evaluation creation response
        self.mock_eval_response = {
            "id": str(uuid4()),
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "batch_size": 1,
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }

        self.template_data = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Test Question",
                    "options": [{"label_text": "Option 1"}],
                }
            ]
        }

    def test_create_evaluator_public_resume_upload_options(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        state_path = os.path.join(temp_dir.name, "state.sqlite")

        # When
        evaluator = self.client.create_evaluator(
            resume_upload=True,
            upload_state_path=state_path,
        )

        # Then
        self.assertTrue(evaluator._eval_config.resume_upload)  # type: ignore[attr-defined]
        self.assertEqual(evaluator._eval_config.upload_state_path, state_path)  # type: ignore[attr-defined]
        self.assertIsNotNone(evaluator._upload_ledger)  # type: ignore[attr-defined]
        self.assertTrue(os.path.exists(state_path))

    @unittest.skipIf(os.name == "nt", "POSIX symlink check")
    def test_create_evaluator_validates_upload_state_path_before_backend_create(self):
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        target_path = os.path.join(temp_dir.name, "target.sqlite")
        symlink_path = os.path.join(temp_dir.name, "state.sqlite")
        with open(target_path, "wb") as f:
            f.write(b"")
        os.symlink(target_path, symlink_path)

        with self.assertRaises(ValueError):
            self.client.create_evaluator(
                resume_upload=True,
                upload_state_path=symlink_path,
            )

        self.api_client.post.assert_not_called()

    def test_resume_evaluator_reuses_existing_evaluation_and_ledger_remote_identity(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        remote_name = "previous-run/remote-object.wav"
        audio_path = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")
        content_md5, file_size = calculate_file_md5_base64(audio_path)
        manifest_audio = Audio(
            path=audio_path,
            name=os.path.basename(audio_path),
            remote_object_name=remote_name,
            script=None,
            tags=[],
            model_tag="model",
            is_ref=False,
            group=None,
            type=QuestionFileType.STIMULUS,
            order_in_group=0,
        )
        manifest_audio.set_integrity_info(content_md5, file_size)

        ledger = UploadLedger(state_path)
        ledger.upsert_queued_file(
            evaluation_id, remote_name, audio_path, file_index=0
        )
        ledger.mark_md5_ready(
            evaluation_id,
            remote_name,
            content_md5,
            file_size,
            manifest_hash=build_upload_manifest_hash(
                manifest_audio.to_create_file_dict(), content_md5, file_size
            ),
        )
        ledger.mark_uploaded(
            evaluation_id,
            remote_name,
            "2026-05-22T00:00:00.000Z",
            "2026-05-22T00:00:01.000Z",
        )
        ledger.mark_metadata_registering(evaluation_id, remote_name)
        ledger.mark_metadata_registered(evaluation_id, remote_name)
        ledger.mark_verified(evaluation_id, remote_name)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(evaluation_id),
        )

        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        evaluator = self.client.resume_evaluator(
            evaluation_id=evaluation_id,
            upload_state_path=state_path,
            max_upload_workers=1,
        )
        evaluator._evaluation_service.process_files = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(processing_count=1)
        )
        evaluator._evaluation_service.upload_session_json = MagicMock()  # type: ignore[method-assign]

        evaluator.add_file(File(path=audio_path, model_tag="model"))
        resumed_audio = evaluator._ordered_file_groups[0].audios[0]  # type: ignore[attr-defined]
        self.assertEqual(resumed_audio.remote_object_name, remote_name)
        result = evaluator.close()

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(evaluator.get_evaluation_id(), evaluation_id)
        self.assertEqual(ledger.counts_by_status(evaluation_id)["verified"], 1)
        self.assertEqual(evaluator._upload_manager._total_files, 0)  # type: ignore[union-attr]

    def test_resume_evaluator_uses_template_id_from_ledger_contract(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        template_id = "template-created-evaluation"
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(evaluation_id, eval_template_id=template_id),
        )

        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        evaluator = self.client.resume_evaluator(
            evaluation_id=evaluation_id,
            upload_state_path=state_path,
        )

        self.assertEqual(evaluator._eval_config.eval_template_id, template_id)  # type: ignore[attr-defined]
        self.assertEqual(evaluator.get_evaluation_id(), evaluation_id)

    def test_resume_evaluator_uses_ranking_batch_size_from_ledger_contract(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(
                evaluation_id,
                eval_type="RANKING",
                eval_batch_size=3,
            ),
        )
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 3,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        evaluator = self.client.resume_evaluator(
            evaluation_id=evaluation_id,
            upload_state_path=state_path,
        )
        evaluator._upload_one_file = MagicMock()  # type: ignore[method-assign]
        audio_path = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")

        evaluator.add_ranking_set(
            [
                File(path=audio_path, model_tag="model-a"),
                File(path=audio_path, model_tag="model-b"),
                File(path=audio_path, model_tag="model-c"),
            ]
        )

        self.assertEqual(evaluator._eval_config.eval_type, EvalType.RANKING)  # type: ignore[attr-defined]
        self.assertEqual(evaluator._eval_config.eval_batch_size, 3)  # type: ignore[attr-defined]
        self.assertEqual(evaluator._upload_one_file.call_count, 3)  # type: ignore[attr-defined]

    def test_resume_ranking_rejects_group_size_that_changes_contract(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(
                evaluation_id,
                eval_type="RANKING",
                eval_batch_size=3,
            ),
        )
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 3,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        evaluator = self.client.resume_evaluator(
            evaluation_id=evaluation_id,
            upload_state_path=state_path,
        )
        evaluator._upload_one_file = MagicMock()  # type: ignore[method-assign]
        evaluator._evaluation_service.update_specific_fields = MagicMock()  # type: ignore[method-assign]
        audio_path = os.path.join(os.path.dirname(__file__), "speech_ch1.mp3")

        with self.assertRaises(ValueError) as context:
            evaluator.add_ranking_set(
                [
                    File(path=audio_path, model_tag="model-a"),
                    File(path=audio_path, model_tag="model-b"),
                ]
            )

        self.assertIn("original evaluation contract", str(context.exception))
        self.assertEqual(evaluator._upload_one_file.call_count, 0)  # type: ignore[attr-defined]
        evaluator._evaluation_service.update_specific_fields.assert_not_called()  # type: ignore[attr-defined]

    def test_resume_evaluator_hydrates_original_session_config_from_ledger(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(
                evaluation_id,
                session_overrides={
                    "eval_name": "original-name",
                    "eval_description": "original-desc",
                    "eval_num": 7,
                    "eval_auto_start": True,
                    "verify_batch_size": 321,
                },
            ),
        )
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        evaluator = self.client.resume_evaluator(
            evaluation_id=evaluation_id,
            upload_state_path=state_path,
            name="wrong-name",
            desc="wrong-desc",
            num_eval=99,
            auto_start=False,
            verify_batch_size=2,
        )

        session_config = evaluator._eval_config.to_dict()  # type: ignore[attr-defined]
        self.assertEqual(session_config["eval_name"], "original-name")
        self.assertEqual(session_config["eval_description"], "original-desc")
        self.assertEqual(session_config["eval_num"], 7)
        self.assertTrue(session_config["eval_auto_start"])
        self.assertEqual(session_config["verify_batch_size"], 321)

    def test_resume_warns_when_the_ledger_overrides_an_explicit_auto_start(self):
        """A stale True from a pre-0.46 ledger charges against an explicit opt-out.

        Ledgers written by 0.44/0.45 already stored eval_auto_start, recorded while the flag
        was inert. Only its effect is new, so a user resuming such a session with
        auto_start=False can be charged for a decision they never made. The override is
        pre-existing behavior; the warning is the part that makes it visible.
        """
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(evaluation_id, session_overrides={"eval_auto_start": True}),
        )
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        with patch("podonos.evaluation.human_evaluation.log.warning") as mock_warning:
            self.client.resume_evaluator(
                evaluation_id=evaluation_id,
                upload_state_path=state_path,
                auto_start=False,
            )

        warnings = " ".join(str(call.args[0]) for call in mock_warning.call_args_list)
        self.assertIn("auto_start=True restored", warnings)
        self.assertIn("charge", warnings)

    def test_resume_evaluator_rejects_contract_without_session_config(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        contract = _resume_contract(evaluation_id)
        contract.pop("session_config")
        ledger.set_evaluation_contract(evaluation_id, contract)
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        with self.assertRaises(ValueError) as context:
            self.client.resume_evaluator(
                evaluation_id=evaluation_id,
                upload_state_path=state_path,
            )

        self.assertIn("missing the original session configuration", str(context.exception))

    def test_resume_evaluator_rejects_backend_batch_size_mismatch(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        ledger = UploadLedger(state_path)
        ledger.set_evaluation_contract(
            evaluation_id,
            _resume_contract(
                evaluation_id,
                eval_type="RANKING",
                eval_batch_size=3,
            ),
        )
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 2,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        with self.assertRaises(ValueError) as context:
            self.client.resume_evaluator(
                evaluation_id=evaluation_id,
                upload_state_path=state_path,
            )

        self.assertIn("Backend evaluation batch_size", str(context.exception))

    def test_resume_evaluator_rejects_path_like_evaluation_id(self):
        with self.assertRaises(ValueError):
            self.client.resume_evaluator(
                evaluation_id="../../api-keys/last-used-time",
                upload_state_path="/tmp/state.sqlite",
            )

    def test_resume_evaluator_rejects_missing_ledger_contract(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "state.sqlite")
        UploadLedger(state_path)
        mock_get_response = MagicMock(status_code=200)
        mock_get_response.json.return_value = {
            "id": evaluation_id,
            "title": "resumed",
            "internal_name": "resumed",
            "batch_size": 1,
            "description": None,
            "status": "DRAFT",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }
        mock_get_response.raise_for_status.return_value = None
        self.api_client.get = MagicMock(return_value=mock_get_response)

        with self.assertRaises(ValueError) as context:
            self.client.resume_evaluator(
                evaluation_id=evaluation_id,
                upload_state_path=state_path,
            )

        self.assertIn("missing the original evaluation contract", str(context.exception))

    def test_resume_evaluator_missing_upload_state_path_does_not_create_ledger(self):
        evaluation_id = str(uuid4())
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        state_path = os.path.join(state_dir.name, "missing-state.sqlite")
        self.assertFalse(os.path.exists(state_path))
        self.api_client.get = MagicMock()

        with self.assertRaises(ValueError) as context:
            self.client.resume_evaluator(
                evaluation_id=evaluation_id,
                upload_state_path=state_path,
            )

        self.assertIn("missing the original evaluation contract", str(context.exception))
        self.assertFalse(os.path.exists(state_path))
        self.api_client.get.assert_not_called()

    def test_create_evaluator_from_json_dict_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data,
            name="Test Evaluation",
            custom_type="SINGLE",
            desc="Test Description",
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path,
                name="Test Evaluation",
                custom_type="SINGLE",
                desc="Test Description",
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
            self.client.create_evaluator_from_template_json(
                json=self.template_data,
                json_file="test.json",
                name="Test",
                custom_type="SINGLE",
            )
        self.assertIn("Only one of", str(context.exception))

    def test_create_evaluator_with_no_json_input(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(
                name="Test", custom_type="SINGLE"
            )
        self.assertIn(
            "Either 'json' or 'json_file' must be provided", str(context.exception)
        )

    def test_create_evaluator_with_invalid_custom_type(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(
                json=self.template_data, name="Test", custom_type="TRIPLE"
            )  # type: ignore
        self.assertIn(
            "custom_type must be one of SINGLE, DOUBLE, SINGLE_REF, RANKING, or RANKING_REF",
            str(context.exception),
        )

    def test_create_evaluator_from_json_dict_with_en_in_language(self):
        """Test creating evaluator from JSON dict with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data,
            name="Test EN-IN Evaluation",
            custom_type="SINGLE",
            desc="Test Description for Indian English",
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_with_en_in_language(self):
        """Test creating evaluator from JSON file with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path,
                name="Test EN-IN Evaluation",
                custom_type="SINGLE",
                desc="Test Description for Indian English",
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.api_client.post.assert_called_once()
            self.assertTrue(self.api_client.put.call_count >= 1)

        finally:
            Path(template_path).unlink()

    def test_create_evaluator_from_template_json_with_ranking_calls_human(self):
        mock_human = MagicMock()
        mock_evaluator = MagicMock()
        mock_human.create_from_template_json.return_value = mock_evaluator
        self.client._human_evaluation = mock_human  # type: ignore

        # RANKING custom_type should succeed
        result = self.client.create_evaluator_from_template_json(
            json={}, name="n", custom_type="RANKING"
        )
        self.assertEqual(result, mock_evaluator)

        # Verify it was called with RANKING
        mock_human.create_from_template_json.assert_called_once()
        call_kwargs = mock_human.create_from_template_json.call_args[1]
        self.assertEqual(call_kwargs["custom_type"], "RANKING")

    def test_create_evaluator_from_template_json_sends_skip_default_questions(self):
        """Test that create_evaluator_from_template_json sends skip_default_questions=True to the API"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        comparison_template = {
            "questions": [
                {
                    "type": "COMPARISON",
                    "question": "Compare quality",
                    "description": "Compare the two audio samples",
                    "scale": 5,
                    "anchor_label": {
                        "title": "Preference",
                        "label_text": {"left": "Better", "right": "Better"},
                    },
                }
            ]
        }

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=comparison_template,
            name="CMOS Test",
            custom_type="SINGLE_REF",
            desc="Test CMOS skip_default_questions",
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        post_data = self.api_client.post.call_args[1].get(
            "data", self.api_client.post.call_args[0][1] if len(self.api_client.post.call_args[0]) > 1 else None
        )
        self.assertTrue(post_data["skip_default_questions"])


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
    def test_env_api_key_only(self, mock_get: Any):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init()
        self.assertTrue(isinstance(mock_client, Client))  # type: ignore

    @mock.patch("requests.get", side_effect=mocked_requests_get)
    def test_both_keys(self, mock_get: Any):
        api_key_env = os.getenv("PODONOS_API_KEY")
        self.assertEqual(api_key_env, "ABCD123ENV")
        mock_client = podonos.init(api_key="ABCD123PARAM")
        self.assertTrue(isinstance(mock_client, Client))  # type: ignore


class TestClient(unittest.TestCase):
    def setUp(self):
        self.valid_api_key = "test_key"
        # Use a real APIClient instance to satisfy strict type checks
        self.api_client = APIClient(self.valid_api_key, "http://testapi.com")
        self.client = Client(self.api_client)

        # Mock successful evaluation creation response
        self.mock_eval_response = {
            "id": str(uuid4()),
            "title": "mock_title",
            "internal_name": "mock_internal_name",
            "batch_size": 1,
            "description": "mock_desc",
            "status": "mock_status",
            "created_time": "2024-03-21T06:18:09.659Z",
            "updated_time": "2024-03-21T06:18:09.659Z",
        }

        self.template_data = {
            "questions": [
                {
                    "type": "SCORED",
                    "question": "Test Question",
                    "options": [{"label_text": "Option 1"}],
                }
            ]
        }

    def test_create_evaluator_public_resume_upload_options(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        state_path = os.path.join(temp_dir.name, "state.sqlite")

        # When
        evaluator = self.client.create_evaluator(
            resume_upload=True,
            upload_state_path=state_path,
        )

        # Then
        self.assertTrue(evaluator._eval_config.resume_upload)  # type: ignore[attr-defined]
        self.assertEqual(evaluator._eval_config.upload_state_path, state_path)  # type: ignore[attr-defined]
        self.assertIsNotNone(evaluator._upload_ledger)  # type: ignore[attr-defined]
        self.assertTrue(os.path.exists(state_path))

    def test_create_evaluator_from_json_dict_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data,
            name="Test Evaluation",
            custom_type="SINGLE",
            desc="Test Description",
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_single(self):
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path,
                name="Test Evaluation",
                custom_type="SINGLE",
                desc="Test Description",
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
            self.client.create_evaluator_from_template_json(
                json=self.template_data,
                json_file="test.json",
                name="Test",
                custom_type="SINGLE",
            )
        self.assertIn("Only one of", str(context.exception))

    def test_create_evaluator_with_no_json_input(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(
                name="Test", custom_type="SINGLE"
            )
        self.assertIn(
            "Either 'json' or 'json_file' must be provided", str(context.exception)
        )

    def test_create_evaluator_with_invalid_custom_type(self):
        # When/Then
        with self.assertRaises(ValueError) as context:
            self.client.create_evaluator_from_template_json(
                json=self.template_data, name="Test", custom_type="TRIPLE"
            )  # type: ignore
        self.assertIn(
            "custom_type must be one of SINGLE, DOUBLE, SINGLE_REF, RANKING, or RANKING_REF",
            str(context.exception),
        )

    def test_create_evaluator_from_json_dict_with_en_in_language(self):
        """Test creating evaluator from JSON dict with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        # When
        evaluator = self.client.create_evaluator_from_template_json(
            json=self.template_data,
            name="Test EN-IN Evaluation",
            custom_type="SINGLE",
            desc="Test Description for Indian English",
        )

        # Then
        self.assertIsInstance(evaluator, Evaluator)
        self.api_client.post.assert_called_once()
        self.assertTrue(self.api_client.put.call_count >= 1)

    def test_create_evaluator_from_json_file_with_en_in_language(self):
        """Test creating evaluator from JSON file with en-in language"""
        # Given
        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = self.mock_eval_response
        mock_post_response.raise_for_status.return_value = None
        self.api_client.post = MagicMock(return_value=mock_post_response)

        mock_put_response = MagicMock(status_code=200)
        mock_put_response.json.return_value = [{"id": str(uuid4())}]
        mock_put_response.raise_for_status.return_value = None
        self.api_client.put = MagicMock(return_value=mock_put_response)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.template_data, f)
            template_path = f.name

        try:
            # When
            evaluator = self.client.create_evaluator_from_template_json(
                json_file=template_path,
                name="Test EN-IN Evaluation",
                custom_type="SINGLE",
                desc="Test Description for Indian English",
            )

            # Then
            self.assertIsInstance(evaluator, Evaluator)
            self.api_client.post.assert_called_once()
            self.assertTrue(self.api_client.put.call_count >= 1)

        finally:
            Path(template_path).unlink()


class TestEvaluatorMethodValidation(unittest.TestCase):
    """Test that evaluator methods are called with the correct evaluation types"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = os.path.dirname(__file__)
        self.audio_path = os.path.join(self.test_dir, "speech_two_ch1.wav")
        self.api_client = APIClient(api_key="test_key", api_url="https://test.api")

        # Mock API responses
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "eval_id",
            "title": "Test Eval",
            "internal_name": "test",
            "description": "test",
            "batch_size": 1,
            "status": "ACTIVE",
            "created_time": "2024-01-01T00:00:00Z",
            "updated_time": "2024-01-01T00:00:00Z",
        }
        mock_response.status_code = 200
        self.api_client.post = Mock(return_value=mock_response)
        self.api_client.put = Mock(return_value=mock_response)

    def test_ranking_evaluator_rejects_add_file(self):
        """Test RANKING evaluator rejects add_file method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.RANKING.value)  # type: ignore
        test_file = File(path=self.audio_path, model_tag="test")

        # When/Then
        with self.assertRaises(ValueError) as context:
            evaluator.add_file(test_file)
        self.assertIn("add_file", str(context.exception))
        self.assertIn("single file evaluation types", str(context.exception))

    def test_ranking_evaluator_rejects_add_files(self):
        """Test RANKING evaluator rejects add_files method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.RANKING.value)  # type: ignore
        file1 = File(path=self.audio_path, model_tag="A")
        file2 = File(path=self.audio_path, model_tag="B")

        # When/Then
        with self.assertRaises(ValueError) as context:
            evaluator.add_files(file1, file2)
        self.assertIn("add_files", str(context.exception))
        self.assertIn("comparison evaluation types", str(context.exception))

    def test_nmos_evaluator_rejects_add_ranking_set(self):
        """Test NMOS evaluator rejects add_ranking_set method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.NMOS.value)  # type: ignore
        files = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]

        # When/Then - add_ranking_set raises ValueError for non-ranking evaluator
        with self.assertRaises(ValueError) as context:
            evaluator.add_ranking_set(files)
        self.assertIn("ranking evaluation types", str(context.exception))

    def test_nmos_evaluator_rejects_add_files(self):
        """Test NMOS evaluator rejects add_files method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.NMOS.value)  # type: ignore
        file1 = File(path=self.audio_path, model_tag="A")
        file2 = File(path=self.audio_path, model_tag="B")

        # When/Then
        with self.assertRaises(ValueError) as context:
            evaluator.add_files(file1, file2)
        self.assertIn("add_files", str(context.exception))
        self.assertIn("comparison evaluation types", str(context.exception))

    def test_pref_evaluator_rejects_add_file(self):
        """Test PREF evaluator rejects add_file method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.PREF.value)  # type: ignore
        test_file = File(path=self.audio_path, model_tag="test")

        # When/Then
        with self.assertRaises(ValueError) as context:
            evaluator.add_file(test_file)
        self.assertIn("add_file", str(context.exception))
        self.assertIn("single file evaluation types", str(context.exception))

    def test_pref_evaluator_rejects_add_ranking_set(self):
        """Test PREF evaluator rejects add_ranking_set method"""
        # Given
        client = Client(api_client=self.api_client)
        evaluator = client._human_evaluation.create(type=EvalType.PREF.value)  # type: ignore
        files = [
            File(path=self.audio_path, model_tag="A"),
            File(path=self.audio_path, model_tag="B"),
        ]

        # When/Then
        with self.assertRaises(ValueError) as context:
            evaluator.add_ranking_set(files)
        self.assertIn("ranking evaluation types", str(context.exception))


@patch("os.path.isfile", return_value=True)
@patch("os.access", return_value=True)
class TestClientFlashEval(unittest.TestCase):
    """Client-level forwarding tests for flash_eval to prevent regressions
    in the public API surface (parameter passthrough to FlashEvalService)."""

    def setUp(self):
        self.valid_api_key = "test_key"
        self.api_client = APIClient(self.valid_api_key, "http://testapi.com")
        self.client = Client(self.api_client)
        # Replace the real service with a mock so we can assert forwarding
        self.client._flash_eval_service = MagicMock()
        self.mock_result = MagicMock()
        self.client._flash_eval_service.eval.return_value = self.mock_result

    def test_flash_eval_forwards_file_path_only(self, mock_access, mock_isfile):
        result = self.client.flash_eval("/path/to/audio.wav")
        self.client._flash_eval_service.eval.assert_called_once_with(
            "/path/to/audio.wav", language=None, category=None
        )
        self.assertIs(result, self.mock_result)

    def test_flash_eval_forwards_language(self, mock_access, mock_isfile):
        self.client.flash_eval("/path/to/audio.wav", language="es-es")
        self.client._flash_eval_service.eval.assert_called_once_with(
            "/path/to/audio.wav", language="es-es", category=None
        )

    def test_flash_eval_forwards_category(self, mock_access, mock_isfile):
        self.client.flash_eval("/path/to/audio.wav", category="noise_quality")
        self.client._flash_eval_service.eval.assert_called_once_with(
            "/path/to/audio.wav", language=None, category="noise_quality"
        )

    def test_flash_eval_forwards_both_language_and_category(self, mock_access, mock_isfile):
        self.client.flash_eval(
            "/path/to/audio.wav", language="es-es", category="noise_quality"
        )
        self.client._flash_eval_service.eval.assert_called_once_with(
            "/path/to/audio.wav", language="es-es", category="noise_quality"
        )

    def test_flash_eval_raises_when_not_initialized(self, mock_access, mock_isfile):
        self.client._initialized = False
        with self.assertRaises(ValueError):
            self.client.flash_eval("/path/to/audio.wav")


if __name__ == "__main__":
    unittest.main(verbosity=2)
