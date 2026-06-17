#!/usr/bin/env python
"""Opt-in dev-server E2E: reproduce the verify-failure -> re-upload path and
prove the exactly-once-registration fix.

Background
----------
The production incident was: a file that had already been registered
(``create_evaluation_files`` / ``PUT evaluations/{id}/files``) failed S3
verification, and the SDK then *re-registered* its metadata on the retry. That
second POST inserted a duplicate ``evaluation_file`` row into the group.

The fix decouples verify-retry from registration: a verify failure means the S3
object was bad, not the metadata, so the SDK must re-upload + re-verify ONLY and
never re-POST ``create_evaluation_files`` for an already-registered file. This
must hold for BOTH configurations:
  * ``resume_upload=False`` (the DEFAULT, and the config the incident ran on) --
    no ledger, the verify-retry path early-returns without re-registering.
  * ``resume_upload=True``  (opt-in ledger) -- the already-acked row is skipped.

How this harness reproduces it (deterministic, no proxy/corruption needed)
--------------------------------------------------------------------------
We do a real upload to the dev server, then force exactly one verify failure in
process so the SDK takes its real retry path against the real backend:

  * Wrap ``EvaluationService.verify_files``: on the FIRST verify call, flip
    exactly one genuinely-verified file to ``verified=False`` (a synthetic
    forced failure) and fix up the response counts. Every later call passes the
    real backend result through, so when the SDK re-uploads that file it
    verifies for real on the retry.
  * Spy on ``EvaluationService.create_evaluation_files``: record the remote
    object names registered on every call.

After ``close()`` we assert:
  * the run completed (``{"status": "ok"}``)            -> the retry path worked
    end to end against the real backend;
  * the forced failure actually fired                   -> not a vacuous pass;
  * ``verify_files`` was called >= 2 times              -> the retry really ran;
  * the failed file was re-verified=True on a later pass -> it was genuinely
    recovered, not silently dropped;
  * every remote_object_name was registered <= once     -> NO re-registration
    (the failed file in particular appears exactly once). This is precisely the
    invariant the bug violated, so a regression would re-register the failed
    file and this assertion would catch it. The create-spy is the *true* witness
    of "no duplicate backend row", because the duplicate was caused precisely by
    the second ``create_evaluation_files`` POST.
  * (ledger only) the ledger ends with one row per file, all ``verified``. This
    guards SDK-local ledger-row integrity; it is NOT an independent witness of
    backend duplication (a re-POST reuses the same remote_object_name key and
    would not create a second ledger row), so the create-spy above remains the
    decisive check.

Group shapes
------------
The incident symptom was a duplicate file *within a group*, so the harness
exercises single- and multi-file groups (``--shape``):
  * single -> NMOS  -- 1 file/group  (add_file)
  * double -> CMOS  -- 1 stimulus + 1 reference per group (add_files)
  * triple -> CSMOS -- 2 stimuli + 1 reference per group  (add_files)
The synthetic failure is injected on exactly one file of one group; the assertion
"that file's remote_object_name is registered exactly once" is the same per-file
invariant in every shape -- a re-registration would add an extra row to its
group, which is precisely the incident.

Scope: a single initial registration/verify batch. ``--items`` x group_size is
capped at 20 files/eval, well under the SDK's 500-file ``create_evaluation_files``
batch size and the pinned per-run verify batch. The >500-file / multi-initial-
batch dimension is out of scope here and is covered by the unit suite.

These hit the real dev backend and perform real presigned-url uploads, so the
script is a no-op unless explicitly enabled. By default it runs every shape x
both configs (6 small evaluations); scope it down with --shape / --config.

Run
---
    # all shapes (single/double/triple) x both configs
    PODONOS_E2E=1 PODONOS_API_KEY=<KEY> \
      python tests/integration/verify_failure_reupload_e2e.py

    # just the triple (CSMOS) shape, default config only, on dev
    PODONOS_E2E=1 PODONOS_API_KEY=<KEY> \
      PODONOS_E2E_BASE_URL=https://dev.podonosapi.com \
      python tests/integration/verify_failure_reupload_e2e.py \
        --shape triple --config no-ledger --items 2

Env / flags
-----------
    PODONOS_E2E=1                  Required opt-in guard.
    PODONOS_API_KEY=<KEY>          Required API key.
    PODONOS_E2E_BASE_URL=<URL>     Defaults to https://dev.podonosapi.com. Must be
                                   a Podonos-owned https host unless
                                   PODONOS_E2E_ALLOW_UNTRUSTED_BASE_URL=1.
    PODONOS_E2E_AUDIO_PATH=<PATH>  Optional audio fixture override.
    --shape {single,double,triple,all}  Group shape(s). Default all.
    --config {both,no-ledger,ledger}    Which config(s) to exercise. Default both.
    --items N                           Groups per evaluation (items x group_size
                                        <= 20). Default 2.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse

# Make the in-tree package importable when run directly as a script
# (python tests/integration/verify_failure_reupload_e2e.py), not only under an
# editable install or `python -m`. Front-insert so the local working copy (the
# code under test, with the fix) wins over any installed podonos.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import podonos  # noqa: E402
from podonos import File  # noqa: E402
from podonos.core.upload_ledger import UploadLedger  # noqa: E402
from podonos.entity.verification import (  # noqa: E402
    VerificationErrorDetail,
    VerifyFilesResponse,
)

_DEV_BASE_URL = "https://dev.podonosapi.com"
_TRUTHY = {"1", "true", "yes", "y", "on"}
_MAX_FILES_PER_EVAL = 20
_DEFAULT_AUDIO_PATH = Path(__file__).resolve().parents[1] / "core" / "speech_ch1.mp3"


@dataclass(frozen=True)
class _Shape:
    """A group shape: how many files the SDK uploads per evaluation item."""

    name: str
    eval_type: str
    group_size: int


# single -> NMOS:  one audio per group           (add_file)
# double -> CMOS:  one stimulus + one reference   (add_files)
# triple -> CSMOS: two stimuli + one reference    (add_files)
_SHAPES = {
    "single": _Shape("single", "NMOS", 1),
    "double": _Shape("double", "CMOS", 2),
    "triple": _Shape("triple", "CSMOS", 3),
}


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def _validate_base_url(base_url: str) -> str:
    if _truthy_env("PODONOS_E2E_ALLOW_UNTRUSTED_BASE_URL"):
        return base_url
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise SystemExit("PODONOS_E2E_BASE_URL must use https.")
    if not (
        host == "podonosapi.com"
        or host.endswith(".podonosapi.com")
        or host == "podonos.com"
        or host.endswith(".podonos.com")
    ):
        raise SystemExit(
            "PODONOS_E2E_BASE_URL must be a Podonos-owned host. Set "
            "PODONOS_E2E_ALLOW_UNTRUSTED_BASE_URL=1 only for intentional local testing."
        )
    return base_url


def _unique_name(prefix: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


class _EnvironmentNotClean(RuntimeError):
    """The real backend state made a trustworthy injection impossible.

    Raised when the initial verify pass is not the single, fully-clean batch the
    harness needs (e.g. the backend genuinely failed a file, fragmented the
    initial verify, or did not round-trip the uploaded file name). This is an
    inconclusive run, not a fix failure -- re-run rather than trusting a verdict
    built on top of real backend noise.
    """


class _ForcedVerifyFailure:
    """One-shot, in-process verify-failure injector + registration spy.

    Wraps the live ``EvaluationService`` bound methods on a single evaluator so
    the SDK takes its real retry path against the real backend, while we observe
    exactly how many times each file's metadata is registered.
    """

    def __init__(self, expected_file_count: int) -> None:
        self.expected_file_count = expected_file_count
        self.verify_calls = 0
        self.injected = False
        self.reverified = False
        self.target: Optional[str] = None
        # One list of remote_object_names per create_evaluation_files call.
        self.register_calls: List[List[str]] = []

    def install(self, service) -> None:
        original_verify: Callable[..., VerifyFilesResponse] = service.verify_files
        original_create: Callable[..., object] = service.create_evaluation_files

        def verify_wrapper(evaluation_id, audios, *args, **kwargs):
            response = original_verify(evaluation_id, audios, *args, **kwargs)
            self.verify_calls += 1
            if not self.injected:
                # Inject strictly on the first verify call. We pin
                # verify_batch_size == file_count so this call IS the whole
                # initial pass; guard that invariant and that the backend gave a
                # clean result, otherwise real backend noise would be folded into
                # the synthetic failure and corrupt the verdict.
                if len(audios) != self.expected_file_count:
                    raise _EnvironmentNotClean(
                        f"initial verify fragmented into a {len(audios)}-file "
                        f"batch; expected a single {self.expected_file_count}-file "
                        "batch."
                    )
                if not (response.all_verified and response.failed_count == 0):
                    raise _EnvironmentNotClean(
                        f"initial verify pass already had {response.failed_count} "
                        "real backend failure(s); cannot inject a clean synthetic "
                        "failure on top of it."
                    )
                self._flip_one_verified(response)
                if self.target_registration_count() < 1:
                    raise _EnvironmentNotClean(
                        f"backend did not round-trip uploaded file name "
                        f"{self.target!r}; it was never registered, so the "
                        "exactly-once check would be meaningless."
                    )
            else:
                # A later (retry) pass: positive witness that the re-uploaded
                # file actually came back verified, so 'registered exactly once'
                # cannot pass vacuously by silently dropping the failed file.
                for result in response.results:
                    if result.uploaded_file_name == self.target and result.verified:
                        self.reverified = True
            return response

        def create_wrapper(evaluation_id, audios, *args, **kwargs):
            self.register_calls.append([a.remote_object_name for a in audios])
            return original_create(evaluation_id, audios, *args, **kwargs)

        service.verify_files = verify_wrapper
        service.create_evaluation_files = create_wrapper

    def _flip_one_verified(self, response: VerifyFilesResponse) -> None:
        for result in response.results:
            if result.verified:
                result.verified = False
                result.error = VerificationErrorDetail(
                    code="E2E_FORCED_FAILURE",
                    message="Synthetic verify failure injected by the E2E harness.",
                )
                response.verified_count = max(0, response.verified_count - 1)
                response.failed_count += 1
                response.all_verified = False
                self.injected = True
                self.target = result.uploaded_file_name
                return

    # -- assertions -----------------------------------------------------------

    def duplicate_registrations(self) -> List[Tuple[str, int]]:
        counts: dict[str, int] = {}
        for names in self.register_calls:
            for name in names:
                counts[name] = counts.get(name, 0) + 1
        return [(name, n) for name, n in counts.items() if n > 1]

    def target_registration_count(self) -> int:
        return sum(names.count(self.target) for names in self.register_calls)


def _add_groups(etor, audio_path: Path, shape: _Shape, items: int) -> None:
    """Queue ``items`` groups of ``shape.group_size`` files each.

    A multi-file group (double/triple) is exactly where "duplicate file in the
    group" -- the original incident symptom -- is meaningful: a re-registration
    of one member would add an extra row to that group.
    """
    path = str(audio_path)
    script = "verify-failure re-upload e2e"
    for i in range(items):
        if shape.group_size == 1:  # NMOS
            etor.add_file(
                File(path=path, model_tag=f"vf_{shape.name}_{i}", script=script)
            )
        elif shape.group_size == 2:  # CMOS: one stimulus + one reference
            etor.add_files(
                file0=File(
                    path=path, model_tag=f"vf_{shape.name}_stim_{i}", script=script
                ),
                file1=File(
                    path=path,
                    model_tag=f"vf_{shape.name}_ref",
                    script=script,
                    is_ref=True,
                ),
            )
        else:  # CSMOS: two distinct-tag stimuli + one reference (ref is 3rd)
            # Double-stimuli types pin a canonical pair of stimulus model_tags
            # across all groups, so a/b must be constant (not per-item).
            etor.add_files(
                file0=File(
                    path=path, model_tag=f"vf_{shape.name}_a", script=script
                ),
                file1=File(
                    path=path, model_tag=f"vf_{shape.name}_b", script=script
                ),
                file2=File(
                    path=path,
                    model_tag=f"vf_{shape.name}_ref",
                    script=script,
                    is_ref=True,
                ),
            )


def _run_config(
    *,
    api_key: str,
    base_url: str,
    audio_path: Path,
    shape: _Shape,
    items: int,
    use_ledger: bool,
) -> Optional[bool]:
    """Return True/False for pass/fail, or None if the run was inconclusive
    (the real backend state made a trustworthy injection impossible)."""
    total_files = items * shape.group_size
    label = "ledger (resume_upload=True)" if use_ledger else "no-ledger (DEFAULT)"
    print(
        f"\n=== shape={shape.name} ({shape.eval_type}, {shape.group_size}/group) "
        f"| config: {label} | items={items} files={total_files} ==="
    )

    client = podonos.init(api_key=api_key, api_url=base_url)

    state_path: Optional[str] = None
    extra_kwargs = {}
    if use_ledger:
        state_dir = tempfile.mkdtemp(prefix="podonos-e2e-verify-fail-")
        state_path = str(Path(state_dir) / "upload-state.sqlite")
        extra_kwargs = {"resume_upload": True, "upload_state_path": state_path}

    etor = client.create_evaluator(
        name=_unique_name(f"sdk-verify-fail-{shape.name}"),
        desc="E2E: verify-failure re-upload must not re-register metadata",
        type=shape.eval_type,
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
        max_upload_workers=2,
        # Force a single initial verify batch so the first verify_files call is
        # the whole initial pass; the injector targets one file from it.
        verify_batch_size=max(1, min(1000, total_files)),
        **extra_kwargs,
    )

    evaluation_id = etor.get_evaluation_id()
    injector = _ForcedVerifyFailure(expected_file_count=total_files)
    injector.install(etor._evaluation_service)  # type: ignore[attr-defined]

    _add_groups(etor, audio_path, shape, items)

    try:
        result = etor.close()
    except _EnvironmentNotClean as exc:
        print(f"  [INCONCLUSIVE] {exc}")
        print(f"  evaluation_id={evaluation_id}")
        return None

    ok = True

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}{(' -> ' + detail) if detail else ''}")

    check("run completed", result == {"status": "ok"}, f"result={result}")
    check(
        "forced verify failure fired",
        injector.injected,
        f"target={injector.target}",
    )
    check(
        "retry path ran (verify_files called >= 2)",
        injector.verify_calls >= 2,
        f"verify_calls={injector.verify_calls}",
    )
    check(
        "failed file re-verified on retry",
        injector.reverified,
        f"reverified={injector.reverified}",
    )
    dupes = injector.duplicate_registrations()
    check(
        "no file registered more than once",
        not dupes,
        f"duplicates={dupes}" if dupes else "all <= 1",
    )
    check(
        "failed file registered exactly once",
        injector.injected and injector.target_registration_count() == 1,
        f"target_count={injector.target_registration_count()}",
    )

    if use_ledger and state_path:
        ledger = UploadLedger(state_path)
        counts = ledger.counts_by_status(evaluation_id)
        check(
            "ledger: every file verified, one row each",
            counts.get("verified", 0) == total_files
            and sum(counts.values()) == total_files,
            f"counts={counts}",
        )

    print(f"  evaluation_id={evaluation_id}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shape",
        choices=["single", "double", "triple", "all"],
        default="all",
        help=(
            "Group shape(s): single=NMOS (1/group), double=CMOS (2/group), "
            "triple=CSMOS (3/group), all=every shape. Default: all."
        ),
    )
    parser.add_argument(
        "--config",
        choices=["both", "no-ledger", "ledger"],
        default="both",
        help="Which configuration(s) to exercise. Default: both.",
    )
    parser.add_argument(
        "--items",
        type=int,
        default=2,
        help="Groups (items) per evaluation. Default: 2.",
    )
    args = parser.parse_args()

    if not (_truthy_env("PODONOS_E2E") or _truthy_env("PODONOS_DEV_E2E")):
        print(
            "Skipped: set PODONOS_E2E=1 and PODONOS_API_KEY to run this real "
            "dev-server E2E.\nExample:\n"
            "  PODONOS_E2E=1 PODONOS_API_KEY=<KEY> "
            "python tests/integration/verify_failure_reupload_e2e.py",
            file=sys.stderr,
        )
        return 2

    api_key = os.getenv("PODONOS_API_KEY")
    if not api_key:
        print("Skipped: set PODONOS_API_KEY to run this E2E.", file=sys.stderr)
        return 2

    shapes = (
        list(_SHAPES.values()) if args.shape == "all" else [_SHAPES[args.shape]]
    )
    if args.items < 1:
        print("--items must be >= 1.", file=sys.stderr)
        return 2
    for shape in shapes:
        if args.items * shape.group_size > _MAX_FILES_PER_EVAL:
            print(
                f"--items={args.items} x {shape.group_size} files/group exceeds the "
                f"{_MAX_FILES_PER_EVAL}-file smoke cap for shape '{shape.name}'.",
                file=sys.stderr,
            )
            return 2

    base_url = _validate_base_url(
        os.getenv("PODONOS_E2E_BASE_URL")
        or os.getenv("PODONOS_DEV_BASE_URL")
        or _DEV_BASE_URL
    )
    audio_path = Path(os.getenv("PODONOS_E2E_AUDIO_PATH", str(_DEFAULT_AUDIO_PATH)))
    if not audio_path.is_file():
        print(f"Audio fixture does not exist: {audio_path}", file=sys.stderr)
        return 2

    configs: List[bool] = []
    if args.config in ("both", "no-ledger"):
        configs.append(False)
    if args.config in ("both", "ledger"):
        configs.append(True)

    print(f"dev-server verify-failure re-upload E2E | base_url={base_url}")
    results: List[Optional[bool]] = []
    for shape in shapes:
        for use_ledger in configs:
            results.append(
                _run_config(
                    api_key=api_key,
                    base_url=base_url,
                    audio_path=audio_path,
                    shape=shape,
                    items=args.items,
                    use_ledger=use_ledger,
                )
            )

    if any(r is None for r in results):
        print(
            "\n=== RESULT: INCONCLUSIVE (backend state not clean for injection; "
            "re-run) ==="
        )
        return 2
    all_ok = all(results)
    print("\n=== RESULT:", "PASS ===" if all_ok else "FAIL ===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
