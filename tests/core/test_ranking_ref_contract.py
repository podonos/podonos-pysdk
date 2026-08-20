"""Contract test for SPEECH_RANKING_REF.

Every silent failure mode of this feature lives in a number the SDK puts on the
wire: whether `batch_size` is stimuli+1, whether the reference's `order` stays
below it, and whether one model_tag holds the same order in every group. None of
those are SDK unit-test concerns -- they are backend invariants, and getting one
wrong produces a wrong invoice rather than an error. This mirrors them client-side.

The mirrors are plain functions so the negative cases at the bottom can feed them
hand-built payloads: `add_ranking_set` cannot produce a group with two references
or a duplicate order, because `_validate_ranking_files` and `AudioGroup.set_audios`
raise first. Without those negative cases a dead mirror would make every assertion
above it vacuous.

This proves the SDK agrees with the rules as transcribed here. It does not ask the
backend anything -- see the plan's "merge-ready is not verified".
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import Mock, patch
from uuid import uuid4

from podonos.common.enum import EvalType, QuestionFileType
from podonos.core.api import APIClient
from podonos.core.config import EvalConfig
from podonos.core.evaluator import Evaluator
from podonos.core.file import File
from podonos.entity.evaluation import EvaluationEntity
from tests.core.test_audio import TESTDATA_SPEECH_TWO_CH1_WAV


def assert_batch_size_is_stimuli_plus_one(
    payloads: List[Dict[str, Any]], batch_size: int
) -> None:
    """Backend: RankingUtil.validate_ranking_reference_groups."""
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for payload in payloads:
        by_group.setdefault(payload["group"], []).append(payload)
    for group, rows in by_group.items():
        stimuli = [r for r in rows if r["type"] != QuestionFileType.REF]
        if len(stimuli) + 1 != batch_size:
            raise AssertionError(
                f"group {group}: stimuli+1 is {len(stimuli) + 1}, batch_size is {batch_size}"
            )


def assert_order_within_group(payloads: List[Dict[str, Any]], batch_size: int) -> None:
    """Backend: ValidateFileDomainService.validate_order_within_group."""
    by_group: Dict[str, List[int]] = {}
    for payload in payloads:
        by_group.setdefault(payload["group"], []).append(payload["order_in_group"])
    for group, orders in by_group.items():
        if any(order >= batch_size for order in orders):
            raise AssertionError(f"group {group}: order >= batch_size {batch_size}: {orders}")
        if len(set(orders)) != len(orders):
            raise AssertionError(f"group {group}: duplicate order: {orders}")


def assert_model_tag_order_injective(payloads: List[Dict[str, Any]]) -> None:
    """Backend: ValidateFileDomainService.validate_model_tag_order_slots.

    One model_tag must hold the same order in every group. This is checked at
    upload time on the SDK's own path, and REF rows are not exempt.
    """
    first_seen: Dict[str, Any] = {}
    for payload in payloads:
        tag = payload["model_tag"]
        seen = first_seen.get(tag)
        if seen is None:
            first_seen[tag] = (payload["group"], payload["order_in_group"])
            continue
        seen_group, expected_order = seen
        if payload["order_in_group"] != expected_order:
            raise AssertionError(
                f"model tag {tag} has order {payload['order_in_group']} in group "
                f"{payload['group']}, but order {expected_order} in group {seen_group}"
            )


def assert_exactly_one_reference_per_group(payloads: List[Dict[str, Any]]) -> None:
    """Backend: RankingUtil.validate_ranking_reference_groups."""
    by_group: Dict[str, List[Dict[str, Any]]] = {}
    for payload in payloads:
        by_group.setdefault(payload["group"], []).append(payload)
    for group, rows in by_group.items():
        refs = [r for r in rows if r["type"] == QuestionFileType.REF]
        if len(refs) != 1:
            raise AssertionError(f"group {group}: {len(refs)} reference(s), expected 1")


class TestRankingRefContract(unittest.TestCase):
    STIMULI = ["model_a", "model_b", "model_c"]
    GROUPS = 3

    def setUp(self):
        self.test_wav = TESTDATA_SPEECH_TWO_CH1_WAV
        self.api_client = Mock(spec=APIClient)
        self.state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_dir.cleanup)
        self.evaluation_id = str(uuid4())

    def _build_evaluator(self) -> Evaluator:
        current_time = datetime.now(timezone.utc)
        evaluation = EvaluationEntity(
            id=self.evaluation_id,
            title="ranking ref",
            internal_name=None,
            description=None,
            batch_size=2,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )
        # resume_upload=True so _update_ranking_batch_size_before_upload runs on the
        # first add_ranking_set, which is what puts batch_size on the wire.
        eval_config = EvalConfig(
            type=EvalType.RANKING_REF.value,
            resume_upload=True,
            upload_state_path=os.path.join(self.state_dir.name, "ledger.sqlite"),
        )
        with patch.object(Evaluator, "_set_evaluation", return_value=evaluation):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.RANKING_REF],
            )
        evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore
        return evaluator

    def _add_groups(self, evaluator: Evaluator) -> None:
        for _ in range(self.GROUPS):
            evaluator.add_ranking_set(
                [
                    File(path=self.test_wav, model_tag=self.STIMULI[0]),
                    File(path=self.test_wav, model_tag=self.STIMULI[1]),
                    File(path=self.test_wav, model_tag=self.STIMULI[2]),
                    # One reference model for the whole evaluation. Distinct tags
                    # per group upload fine but split the summary's reference row.
                    File(path=self.test_wav, model_tag="reference", is_ref=True),
                ]
            )

    @patch.object(Evaluator, "_upload_one_file")
    def test_upload_payload_satisfies_backend_invariants(self, _mock_upload: Mock):
        evaluator = self._build_evaluator()
        self._add_groups(evaluator)

        payloads = [
            audio.to_create_file_dict()
            for group in evaluator._ordered_file_groups  # type: ignore[attr-defined]
            for audio in group.audios
        ]
        sent = evaluator._evaluation_service.update_specific_fields.call_args[0][1]  # type: ignore
        batch_size = sent["batch_size"]

        # (a) batch_size is stimuli + 1. The backend divides total files by this to
        # count billable queries, so a wrong value is a wrong invoice.
        self.assertEqual(batch_size, len(self.STIMULI) + 1)
        assert_batch_size_is_stimuli_plus_one(payloads, batch_size)

        # (b) every order is below batch_size and unique within its group
        assert_order_within_group(payloads, batch_size)

        # (c) model_tag -> order is injective across groups, references included
        assert_model_tag_order_injective(payloads)

        # (d) exactly one reference per group, stored last
        assert_exactly_one_reference_per_group(payloads)
        for group in evaluator._ordered_file_groups:  # type: ignore[attr-defined]
            refs = [a for a in group.audios if a.type == QuestionFileType.REF]
            self.assertEqual(len(refs), 1)
            self.assertEqual(
                refs[0].order_in_group,
                max(a.order_in_group for a in group.audios),
            )

        # (e) the evaluation_type on the wire is what selects the price tier
        self.assertEqual(sent["evaluation_type"], "SPEECH_RANKING_REF")

    @patch.object(Evaluator, "_upload_one_file")
    def test_plain_ranking_payload_is_unchanged(self, _mock_upload: Mock):
        """Same invariants minus the reference, so a RANKING regression shows up here."""
        current_time = datetime.now(timezone.utc)
        evaluation = EvaluationEntity(
            id=self.evaluation_id,
            title="ranking",
            internal_name=None,
            description=None,
            batch_size=2,
            status="DRAFT",
            created_time=current_time,
            updated_time=current_time,
        )
        eval_config = EvalConfig(
            type=EvalType.RANKING.value,
            resume_upload=True,
            upload_state_path=os.path.join(self.state_dir.name, "plain.sqlite"),
        )
        with patch.object(Evaluator, "_set_evaluation", return_value=evaluation):
            evaluator = Evaluator(
                api_client=self.api_client,
                eval_config=eval_config,
                supported_eval_types=[EvalType.RANKING],
            )
        evaluator._evaluation_service.update_specific_fields = Mock()  # type: ignore

        for _ in range(self.GROUPS):
            evaluator.add_ranking_set(
                [File(path=self.test_wav, model_tag=tag) for tag in self.STIMULI]
            )

        payloads = [
            audio.to_create_file_dict()
            for group in evaluator._ordered_file_groups  # type: ignore[attr-defined]
            for audio in group.audios
        ]
        sent = evaluator._evaluation_service.update_specific_fields.call_args[0][1]  # type: ignore
        self.assertEqual(sent["batch_size"], len(self.STIMULI))
        self.assertEqual(sent["evaluation_type"], "SPEECH_RANKING")
        assert_order_within_group(payloads, sent["batch_size"])
        assert_model_tag_order_injective(payloads)


class TestRankingRefContractMirrorsCatchViolations(unittest.TestCase):
    """The mirrors above are only worth anything if they fail on bad input.

    These payloads cannot be produced through `add_ranking_set` -- validation and
    `AudioGroup.set_audios` reject them first -- so they are built by hand.
    """

    def _row(self, group: str, tag: str, order: int, is_ref: bool = False):
        return {
            "group": group,
            "model_tag": tag,
            "order_in_group": order,
            "type": QuestionFileType.REF if is_ref else QuestionFileType.STIMULUS,
        }

    def test_batch_size_mirror_catches_a_reference_excluded_from_the_count(self):
        payloads = [
            self._row("g1", "a", 0),
            self._row("g1", "b", 1),
            self._row("g1", "r", 2, is_ref=True),
        ]
        with self.assertRaises(AssertionError):
            assert_batch_size_is_stimuli_plus_one(payloads, batch_size=2)

    def test_order_mirror_catches_a_duplicate_order(self):
        payloads = [
            self._row("g1", "a", 0),
            self._row("g1", "b", 0),
            self._row("g1", "r", 2, is_ref=True),
        ]
        with self.assertRaises(AssertionError):
            assert_order_within_group(payloads, batch_size=3)

    def test_order_mirror_catches_an_order_at_or_above_batch_size(self):
        payloads = [self._row("g1", "a", 0), self._row("g1", "r", 3, is_ref=True)]
        with self.assertRaises(AssertionError):
            assert_order_within_group(payloads, batch_size=3)

    def test_injectivity_mirror_catches_a_tag_at_two_orders(self):
        payloads = [
            self._row("g1", "a", 0),
            self._row("g1", "b", 1),
            self._row("g2", "b", 0),
            self._row("g2", "a", 1),
        ]
        with self.assertRaises(AssertionError):
            assert_model_tag_order_injective(payloads)

    def test_reference_count_mirror_catches_two_references(self):
        payloads = [
            self._row("g1", "a", 0),
            self._row("g1", "r1", 1, is_ref=True),
            self._row("g1", "r2", 2, is_ref=True),
        ]
        with self.assertRaises(AssertionError):
            assert_exactly_one_reference_per_group(payloads)

    def test_reference_count_mirror_catches_a_missing_reference(self):
        payloads = [self._row("g1", "a", 0), self._row("g1", "b", 1)]
        with self.assertRaises(AssertionError):
            assert_exactly_one_reference_per_group(payloads)


if __name__ == "__main__":
    unittest.main()
