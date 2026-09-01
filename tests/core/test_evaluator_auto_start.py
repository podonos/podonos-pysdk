"""Tests for the auto_start readiness-then-start poll in Evaluator.close().

These drive the real APIClient and EvaluationService by patching `requests.get` and
`requests.post`, so the transport's own retry and exception handling are exercised rather than
mocked away. That matters: several of the behaviours under test are about how the poll loop
composes with the transport retry, and a test that stubbed the service out could not see them.
"""

import itertools
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from requests import Response
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout as RequestsReadTimeout

from podonos.common.enum import EvalType
from podonos.common.exception import HTTPError
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.entity.evaluation import EvaluationEntity

# The poll methods validate this as a UUID, so the fixture has to be a real one.
EVALUATION_ID = "3f2a1c94-6b5d-4e18-9a7c-2d0e8b5f1a63"


def _response(status_code: int, body=None, text: str = "") -> Response:
    response = Response()
    response.status_code = status_code
    response._content = json.dumps(body).encode() if body is not None else text.encode()
    return response


def _started(status: str = "ACTIVE") -> Response:
    return _response(
        200,
        {
            "evaluation_id": EVALUATION_ID,
            "status": status,
            "internal_status": "EVAL_START",
            "started_time": "2026-08-31T00:00:00Z",
        },
    )


def _not_ready() -> Response:
    return _response(409, {"error_code": "AUDIO_FILES_NOT_READY_IN_EVALUATION", "error_message": "not ready"})


class TestEvaluatorAutoStart(unittest.TestCase):
    def setUp(self):
        self.api_client = APIClient(
            api_key="test-key",
            api_url="https://api.test",
            max_retries=1,
            retry_delay=0,
            backoff_factor=1,
        )
        current_time = datetime.now(timezone.utc)
        self.evaluation = EvaluationEntity(
            id=EVALUATION_ID,
            title="test_title",
            internal_name=None,
            description=None,
            batch_size=1,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )

    def _evaluator(self, auto_start: bool = True, start_timeout: float = 1800) -> Evaluator:
        with patch.object(Evaluator, "_set_evaluation", return_value=self.evaluation):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=EvalConfig(
                    type=EvalType.NMOS.value,
                    auto_start=auto_start,
                    start_timeout=start_timeout,
                ),
                supported_eval_types=[EvalType.NMOS],
            )
        evaluator._evaluation = self.evaluation  # type: ignore
        return evaluator

    # ---- phase 1: readiness -------------------------------------------------

    @patch("podonos.core.evaluator.random.uniform", return_value=0.0)
    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_polls_through_409s_then_starts_on_first_200(self, mock_get, mock_post, mock_sleep, _uniform):
        mock_get.side_effect = [_not_ready(), _not_ready(), _response(200)]
        mock_post.return_value = _started()

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_post.call_count, 1)

    @patch("podonos.core.evaluator.random.uniform", return_value=0.0)
    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_poll_backoff_delays_are_5_10_20_30_30(self, mock_get, mock_post, mock_sleep, _uniform):
        mock_get.side_effect = [_not_ready()] * 5 + [_response(200)]
        mock_post.return_value = _started()

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertEqual(delays, [5, 10, 20, 30, 30])

    @patch("podonos.core.evaluator.random.uniform", return_value=0.3)
    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_poll_backoff_applies_jitter_within_bounds(self, mock_get, mock_post, mock_sleep, _uniform):
        mock_get.side_effect = [_not_ready(), _response(200)]
        mock_post.return_value = _started()

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        # 5 base + 0.3 * 5 jitter. Without jitter a synchronized fleet of CI jobs sharing one
        # API key would poll in lockstep.
        self.assertEqual(mock_sleep.call_args_list[0].args[0], 6.5)
        # Assert the range too, not just the arithmetic on it: without this the test passes
        # against any uniform(a, b) that happens to return 0.3.
        _uniform.assert_called_once_with(0.1, 0.3)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_transport_exhausted_429_is_absorbed_and_polling_continues(self, mock_get, mock_post, mock_sleep):
        # APIClient retries a 429 itself, then raises once its own attempts are exhausted.
        # The poll loop must treat that as one more tick, not as an answer.
        mock_get.side_effect = [_response(429), _response(429), _response(200)]
        mock_post.return_value = _started()

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_post.call_count, 1)

    # ---- phase 2: start -----------------------------------------------------

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_status_active_ends_the_loop(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.return_value = _started("ACTIVE")

        # start_timeout=1 so a membership regression fails fast instead of looping for 30 minutes.
        self._evaluator(start_timeout=1)._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_status_completed_ends_the_loop(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.return_value = _started("COMPLETED")

        self._evaluator(start_timeout=1)._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_200_with_unexpected_status_retries_start(self, mock_get, mock_post, mock_sleep):
        """A 200 carrying a status that is not started must not be read as success.

        This is the only test that separates membership from truthiness. An implementation
        written as `if status:` or `if status is not None:` returns after the first POST and
        reports a DRAFT evaluation as started -- a silent non-start, which is the bug this
        feature exists to remove. Both wrong forms fail the call-count assertion below.
        """
        mock_get.return_value = _response(200)
        mock_post.side_effect = [_started("DRAFT"), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_409_after_lost_response_retries_start_and_never_revalidates(self, mock_get, mock_post, mock_sleep):
        """After a start has been issued, validate must never be called again.

        validate is DRAFT-only. If the start actually succeeded and its response was lost, a
        re-validation answers 400 BAD_REQUEST_EVALUATION_NOT_DRAFT and close() would raise on an
        evaluation the user has already paid for.
        """
        mock_get.return_value = _response(200)
        mock_post.side_effect = [
            _response(409, {"error_code": "CONFLICT_EVALUATION_START_IN_PROGRESS", "error_message": "in progress"}),
            _started("ACTIVE"),
        ]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_lost_start_on_active_evaluation_resolves_as_success(self, mock_get, mock_post, mock_sleep):
        """The retry, not the first call, is what observes ACTIVE -- the idempotency guarantee."""
        mock_get.return_value = _response(200)
        # A read timeout is the true lost-response case: the request reached the server, which
        # may have started and charged the evaluation, but the reply never came back. The retry
        # observes ACTIVE via the idempotent path rather than starting anything itself.
        mock_post.side_effect = [RequestsReadTimeout("read timed out"), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_transport_exhausted_429_on_start_is_absorbed_and_start_retried(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.side_effect = [_response(429), _response(429), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 3)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_network_exception_on_start_is_absorbed(self, mock_get, mock_post, mock_sleep):
        """A start whose response never arrived may still have succeeded and charged.

        Raising here would report failure on a possibly-charged evaluation; retrying the
        idempotent start resolves it.
        """
        mock_get.return_value = _response(200)
        mock_post.side_effect = [RequestsConnectionError("connection reset"), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_200_with_unparseable_body_is_treated_as_a_tick(self, mock_get, mock_post, mock_sleep):
        """A 2xx that is not the expected object must not escape as a raw requests exception.

        An ingress or proxy returning HTML with a 200 is the realistic case. requests'
        JSONDecodeError subclasses ValueError, so the guard is narrow rather than blanket.
        """
        mock_get.return_value = _response(200)
        mock_post.side_effect = [_response(200, text="<html>gateway</html>"), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_200_with_json_list_body_is_treated_as_a_tick(self, mock_get, mock_post, mock_sleep):
        """A body that parses but is not a mapping raises AttributeError on .get, not ValueError."""
        mock_get.return_value = _response(200)
        mock_post.side_effect = [_response(200, [1, 2]), _started("ACTIVE")]

        self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_post.call_count, 2)

    # ---- terminal failures --------------------------------------------------

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_deleted_evaluation_mid_poll_raises_and_never_reports_started(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            400, {"error_code": "BAD_REQUEST_EVALUATION_NOT_STARTABLE", "error_message": "cannot be started"}
        )

        with self.assertRaises(HTTPError) as context:
            self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertIn("BAD_REQUEST_EVALUATION_NOT_STARTABLE", str(context.exception))

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_insufficient_balance_surfaces_error_code_in_message(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            400, {"error_code": "BILLING_INSUFFICIENT_BALANCE", "error_message": "Not enough balance."}
        )

        with self.assertRaises(HTTPError) as context:
            self._evaluator()._start_evaluation_when_ready()  # type: ignore

        message = str(context.exception)
        self.assertIn("BILLING_INSUFFICIENT_BALANCE", message)
        self.assertIn("Not enough balance.", message)

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_terminal_4xx_raises_even_when_error_code_suggests_already_started(self, mock_get, mock_post, mock_sleep):
        """Success is the status field of a 200, never an inference from an error code."""
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            400, {"error_code": "BILLING_EVALUATION_ALREADY_STARTED", "error_message": "already started"}
        )

        with self.assertRaises(HTTPError):
            self._evaluator()._start_evaluation_when_ready()  # type: ignore

    @patch("time.sleep")
    @patch("requests.get")
    def test_invalid_audio_files_in_phase_one_raises(self, mock_get, mock_sleep):
        mock_get.return_value = _response(
            400, {"error_code": "INVALID_AUDIO_FILES_IN_EVALUATION", "error_message": "replace the files"}
        )

        with self.assertRaises(HTTPError) as context:
            self._evaluator()._start_evaluation_when_ready()  # type: ignore

        self.assertIn("INVALID_AUDIO_FILES_IN_EVALUATION", str(context.exception))

    # ---- deadline -----------------------------------------------------------

    @patch("podonos.core.evaluator.time.monotonic", side_effect=itertools.count(0, 1000))
    @patch("time.sleep")
    @patch("requests.get")
    def test_start_timeout_exceeded_raises_timeout_error(self, mock_get, mock_sleep, _monotonic):
        # started_at=0, deadline=1800. First tick at 1000 sleeps; the second reads 2000 and trips.
        mock_get.return_value = _not_ready()

        with self.assertRaises(TimeoutError) as context:
            self._evaluator(start_timeout=1800)._start_evaluation_when_ready()  # type: ignore

        message = str(context.exception)
        self.assertIn("waited 2000s", message)
        self.assertIn("1800s start_timeout", message)
        self.assertIn("files not ready", message)

    @patch("podonos.core.evaluator.time.monotonic", side_effect=itertools.count(0, 1000))
    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_start_timeout_in_phase_two_reports_last_start_status(self, mock_get, mock_post, mock_sleep, _monotonic):
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            409, {"error_code": "CONFLICT_EVALUATION_START_IN_PROGRESS", "error_message": "in progress"}
        )

        with self.assertRaises(TimeoutError) as context:
            self._evaluator(start_timeout=1800)._start_evaluation_when_ready()  # type: ignore

        self.assertIn("start returned None", str(context.exception))

    @patch("requests.post")
    @patch("requests.get")
    def test_already_started_evaluation_is_not_polled(self, mock_get, mock_post):
        """Entering the readiness phase on a running evaluation would raise on a charged run.

        validate is DRAFT-only. A resumed session whose start already succeeded is ACTIVE, so
        polling it answers 400 BAD_REQUEST_EVALUATION_NOT_DRAFT and close() would report failure
        on an evaluation the user has already paid for.
        """
        for status in ("ACTIVE", "COMPLETED"):
            with self.subTest(status=status):
                mock_get.reset_mock()
                mock_post.reset_mock()
                evaluator = self._evaluator()
                evaluator._evaluation.status = status  # type: ignore

                evaluator._start_evaluation_when_ready()  # type: ignore

                mock_get.assert_not_called()
                mock_post.assert_not_called()

    # started_at=0, first tick at 5s of a 7s budget (2s left, 5s backoff due), then the deadline.
    @patch("podonos.core.evaluator.time.monotonic", side_effect=[0, 5, 7])
    @patch("time.sleep")
    @patch("requests.get")
    def test_poll_sleep_is_clamped_to_the_remaining_budget(self, mock_get, mock_sleep, _monotonic):
        """start_timeout must bound the wall clock, not just gate the next request.

        With 2s left and a 5s backoff due, an unclamped sleep overshoots the deadline by 3s --
        and at production APIClient defaults the overshoot compounds well past the budget.
        """
        mock_get.return_value = _not_ready()

        with self.assertRaises(TimeoutError):
            self._evaluator(start_timeout=7)._start_evaluation_when_ready()  # type: ignore

        self.assertEqual(mock_sleep.call_args_list[0].args[0], 2)

    @patch("podonos.core.evaluator.time.monotonic", side_effect=itertools.count(0, 1000))
    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_phase_two_timeout_does_not_claim_the_evaluation_did_not_start(self, mock_get, mock_post, mock_sleep, _monotonic):
        """Every phase-2 tick is consistent with a start that succeeded and charged.

        Telling the user it "did not start" invites them to run it again and pay twice.
        """
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            409, {"error_code": "CONFLICT_EVALUATION_START_IN_PROGRESS", "error_message": "in progress"}
        )

        with self.assertRaises(TimeoutError) as context:
            self._evaluator(start_timeout=1800)._start_evaluation_when_ready()  # type: ignore

        message = str(context.exception)
        self.assertIn("could not confirm the start", message)
        self.assertNotIn("did not start", message)

    @patch("podonos.core.evaluator.time.monotonic", side_effect=itertools.count(0, 1000))
    @patch("time.sleep")
    @patch("requests.get")
    def test_phase_one_timeout_may_still_say_it_did_not_start(self, mock_get, mock_sleep, _monotonic):
        """Phase 1 never issues a start, so the definitive wording is accurate there."""
        mock_get.return_value = _not_ready()

        with self.assertRaises(TimeoutError) as context:
            self._evaluator(start_timeout=1800)._start_evaluation_when_ready()  # type: ignore

        self.assertIn("did not start", str(context.exception))

    # ---- close() integration ------------------------------------------------

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_close_runs_auto_start_phase_between_upload_and_cleanup(self, mock_get, mock_post, mock_sleep):
        """Ordering only: this patches the auto_start phase out, so it proves where the phase
        sits in close(), not that it blocks or starts anything. The behaviour of the phase
        itself is covered by the phase-1 and phase-2 tests above."""
        mock_get.return_value = _response(200)
        mock_post.return_value = _started("ACTIVE")
        evaluator = self._evaluator()
        recorder = Mock()

        with patch.object(evaluator, "_wait_for_uploads", recorder.wait_for_uploads), patch.object(
            evaluator, "_process_audio_files_with_verification", recorder.process
        ), patch.object(evaluator, "_upload_session_json", recorder.upload_session), patch.object(
            evaluator, "_start_evaluation_when_ready", recorder.start_when_ready
        ), patch.object(evaluator, "_cleanup", recorder.cleanup):
            result = evaluator.close()

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            [call[0] for call in recorder.mock_calls],
            ["wait_for_uploads", "process", "upload_session", "start_when_ready", "cleanup"],
        )

    @patch("requests.post")
    @patch("requests.get")
    def test_auto_start_false_makes_no_validate_or_start_call(self, mock_get, mock_post):
        evaluator = self._evaluator(auto_start=False)

        with patch.object(evaluator, "_wait_for_uploads"), patch.object(
            evaluator, "_process_audio_files_with_verification"
        ), patch.object(evaluator, "_upload_session_json"):
            result = evaluator.close()

        self.assertEqual(result, {"status": "ok"})
        mock_get.assert_not_called()
        mock_post.assert_not_called()
        # _cleanup() still ran, exactly as it did before this feature existed.
        self.assertFalse(evaluator._initialized)  # type: ignore

    @patch("time.sleep")
    @patch("requests.post")
    @patch("requests.get")
    def test_close_cleans_up_even_when_start_raises(self, mock_get, mock_post, mock_sleep):
        mock_get.return_value = _response(200)
        mock_post.return_value = _response(
            400, {"error_code": "BILLING_INSUFFICIENT_BALANCE", "error_message": "Not enough balance."}
        )
        evaluator = self._evaluator()

        with patch.object(evaluator, "_wait_for_uploads"), patch.object(
            evaluator, "_process_audio_files_with_verification"
        ), patch.object(evaluator, "_upload_session_json"):
            with self.assertRaises(HTTPError):
                evaluator.close()

        self.assertFalse(evaluator._initialized)  # type: ignore


if __name__ == "__main__":
    unittest.main()
