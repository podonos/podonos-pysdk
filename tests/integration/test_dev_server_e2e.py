"""
Opt-in dev-server E2E tests for real SDK upload/verify flows.

These tests intentionally hit the configured Podonos backend and perform real
presigned-url uploads, so they are skipped unless explicitly enabled.

Run examples:
    PODONOS_E2E=1 PODONOS_API_KEY=<KEY> \
      python -m pytest tests/integration/test_dev_server_e2e.py -q -s

    PODONOS_E2E=1 PODONOS_API_KEY=<KEY> \
      PODONOS_E2E_BASE_URL=https://dev.podonosapi.com \
      PODONOS_E2E_FILE_COUNT=3 \
      python -m pytest tests/integration/test_dev_server_e2e.py -q -s

    # Explicit CMOS smoke run. PODONOS_E2E_FILE_COUNT is the total file count,
    # so it must be even; 2 files means 1 CMOS stimulus/reference pair.
    PODONOS_E2E=1 PODONOS_E2E_CMOS=1 PODONOS_API_KEY=<KEY> \
      PODONOS_E2E_FILE_COUNT=2 \
      python -m pytest tests/integration/test_dev_server_e2e.py::test_dev_server_cmos_upload_verify_with_opt_in_ledger -q -s

    # Explicit large-load run. This intentionally uploads 5000 real files to
    # the configured backend, so it has a second opt-in guard and targets only
    # the load test. Set PODONOS_E2E_EVAL_TYPE=CMOS to run the same 5000-file
    # load path as 2500 CMOS stimulus/reference pairs.
    PODONOS_E2E=1 PODONOS_E2E_LOAD=1 PODONOS_API_KEY=<KEY> \
      PODONOS_E2E_FILE_COUNT=5000 \
      PODONOS_E2E_MAX_UPLOAD_WORKERS=20 \
      PODONOS_E2E_VERIFY_BATCH_SIZE=500 \
      python -m pytest tests/integration/test_dev_server_e2e.py::test_dev_server_upload_verify_large_file_count_with_opt_in_ledger -q -s

Useful env vars:
    PODONOS_E2E=1                         Required opt-in guard.
    PODONOS_API_KEY=<KEY>                 Required API key.
    PODONOS_E2E_BASE_URL=<URL>            Defaults to https://dev.podonosapi.com.
    PODONOS_E2E_FILE_COUNT=<N>            Defaults to 2; capped at 20 for smoke safety.
                                           For CMOS, this is total files and must be even.
    PODONOS_E2E_CMOS=1                    Required for the dedicated CMOS smoke test.
    PODONOS_E2E_EVAL_TYPE=NMOS|CMOS       Defaults to NMOS for the large-load test.
    PODONOS_E2E_LOAD=1                    Required for >20-file load tests.
    PODONOS_E2E_MAX_UPLOAD_WORKERS=<N>    Defaults to 2 for smoke, 20 for load.
    PODONOS_E2E_VERIFY_BATCH_SIZE=<N>     Defaults to 2 for smoke, 500 for load.
    PODONOS_E2E_PROGRESS_EVERY=<N>        Defaults to 100 for smoke, 500 for load.
    PODONOS_E2E_AUDIO_PATH=/path/a.wav    Optional audio fixture override.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest

import podonos
from podonos import File
from podonos.core.upload_ledger import UploadLedger


_DEV_BASE_URL = "https://dev.podonosapi.com"
_TRUTHY = {"1", "true", "yes", "y", "on"}
_MAX_SMOKE_FILE_COUNT = 20
_MAX_LOAD_FILE_COUNT = 10_000
_DEFAULT_AUDIO_PATH = Path(__file__).resolve().parents[1] / "core" / "speech_ch1.mp3"


@dataclass(frozen=True)
class DevServerSettings:
    api_key: str
    base_url: str
    file_count: int
    audio_path: Path
    load_mode: bool
    max_upload_workers: int
    verify_batch_size: int
    api_timeout: tuple[float, float]
    verify_timeout: tuple[float, float]
    upload_timeout: tuple[float, float]
    progress_every: int
    eval_type: str


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        pytest.fail(f"{name} must be an integer, got {raw!r}")


def _timeout_env(name: str, default: tuple[float, float]) -> tuple[float, float]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 2:
        pytest.fail(f"{name} must be '<connect>,<read>', got {raw!r}")

    try:
        timeout = (float(parts[0]), float(parts[1]))
    except ValueError:
        pytest.fail(f"{name} must contain numeric timeout values, got {raw!r}")

    if timeout[0] <= 0 or timeout[1] <= 0:
        pytest.fail(f"{name} timeout values must be positive, got {raw!r}")
    return timeout


def _validate_e2e_base_url(base_url: str) -> str:
    if _truthy_env("PODONOS_E2E_ALLOW_UNTRUSTED_BASE_URL"):
        return base_url

    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        pytest.fail("PODONOS_E2E_BASE_URL must use https.")
    if not (
        host == "podonosapi.com"
        or host.endswith(".podonosapi.com")
        or host == "podonos.com"
        or host.endswith(".podonos.com")
    ):
        pytest.fail(
            "PODONOS_E2E_BASE_URL must be a Podonos-owned host. "
            "Set PODONOS_E2E_ALLOW_UNTRUSTED_BASE_URL=1 only for intentional local testing."
        )
    return base_url


@pytest.fixture(scope="session")
def dev_server_settings() -> DevServerSettings:
    if not (_truthy_env("PODONOS_E2E") or _truthy_env("PODONOS_DEV_E2E")):
        pytest.skip("Set PODONOS_E2E=1 to run real dev-server E2E tests.")

    api_key = os.getenv("PODONOS_API_KEY")
    if not api_key:
        pytest.skip("Set PODONOS_API_KEY to run dev-server E2E tests.")

    base_url = (
        os.getenv("PODONOS_E2E_BASE_URL")
        or os.getenv("PODONOS_DEV_BASE_URL")
        or _DEV_BASE_URL
    )
    base_url = _validate_e2e_base_url(base_url)
    load_mode = _truthy_env("PODONOS_E2E_LOAD") or _truthy_env(
        "PODONOS_E2E_ALLOW_LOAD"
    )
    file_count = _int_env("PODONOS_E2E_FILE_COUNT", 2)
    if file_count < 1:
        pytest.fail("PODONOS_E2E_FILE_COUNT must be >= 1")
    if file_count > _MAX_SMOKE_FILE_COUNT and not load_mode:
        pytest.fail(
            "PODONOS_E2E_FILE_COUNT must be between 1 and "
            f"{_MAX_SMOKE_FILE_COUNT} for smoke tests. For a real large-load "
            "E2E run, add PODONOS_E2E_LOAD=1 and target "
            "test_dev_server_upload_verify_large_file_count_with_opt_in_ledger."
        )
    if file_count > _MAX_LOAD_FILE_COUNT:
        pytest.fail(
            f"PODONOS_E2E_FILE_COUNT is capped at {_MAX_LOAD_FILE_COUNT} by this "
            "test harness. Raise _MAX_LOAD_FILE_COUNT intentionally if needed."
        )

    max_upload_workers = _int_env(
        "PODONOS_E2E_MAX_UPLOAD_WORKERS", 20 if load_mode else 2
    )
    verify_batch_size = _int_env(
        "PODONOS_E2E_VERIFY_BATCH_SIZE", 500 if load_mode else 2
    )
    progress_every = _int_env("PODONOS_E2E_PROGRESS_EVERY", 500 if load_mode else 100)
    eval_type = os.getenv("PODONOS_E2E_EVAL_TYPE", "NMOS").strip().upper()
    if eval_type not in {"NMOS", "CMOS"}:
        pytest.fail("PODONOS_E2E_EVAL_TYPE must be NMOS or CMOS")
    if max_upload_workers < 1:
        pytest.fail("PODONOS_E2E_MAX_UPLOAD_WORKERS must be >= 1")
    if verify_batch_size < 1 or verify_batch_size > 1000:
        pytest.fail("PODONOS_E2E_VERIFY_BATCH_SIZE must be between 1 and 1000")
    if progress_every < 1:
        pytest.fail("PODONOS_E2E_PROGRESS_EVERY must be >= 1")

    audio_path = Path(os.getenv("PODONOS_E2E_AUDIO_PATH", str(_DEFAULT_AUDIO_PATH)))
    if not audio_path.is_file():
        pytest.fail(f"E2E audio fixture does not exist: {audio_path}")

    return DevServerSettings(
        api_key=api_key,
        base_url=base_url,
        file_count=file_count,
        audio_path=audio_path,
        load_mode=load_mode,
        max_upload_workers=max_upload_workers,
        verify_batch_size=verify_batch_size,
        api_timeout=_timeout_env("PODONOS_E2E_API_TIMEOUT", (5, 30)),
        verify_timeout=_timeout_env("PODONOS_E2E_VERIFY_TIMEOUT", (5, 120)),
        upload_timeout=_timeout_env("PODONOS_E2E_UPLOAD_TIMEOUT", (10, 300)),
        progress_every=progress_every,
        eval_type=eval_type,
    )


def _new_client(settings: DevServerSettings):
    return podonos.init(api_key=settings.api_key, api_url=settings.base_url)


def _unique_name(prefix: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _skip_smoke_in_load_mode(settings: DevServerSettings) -> None:
    if settings.load_mode:
        pytest.skip(
            "PODONOS_E2E_LOAD=1 is for the dedicated large-load test; "
            "smoke tests are skipped to avoid duplicate uploads."
        )


def _skip_unless_cmos_enabled() -> None:
    if not _truthy_env("PODONOS_E2E_CMOS"):
        pytest.skip("Set PODONOS_E2E_CMOS=1 to run CMOS dev-server E2E tests.")


def _add_files(
    etor,
    audio_path: Path,
    file_count: int,
    model_prefix: str,
    progress_every: int,
) -> None:
    for index in range(file_count):
        etor.add_file(
            File(
                path=str(audio_path),
                model_tag=f"{model_prefix}_{index % 5}",
                script="dev server e2e test",
            )
        )
        if (index + 1) % progress_every == 0 or index + 1 == file_count:
            print(f"queued {index + 1}/{file_count} files")


def _cmos_pair_count(file_count: int) -> int:
    if file_count < 2:
        pytest.fail("CMOS E2E requires PODONOS_E2E_FILE_COUNT >= 2")
    if file_count % 2 != 0:
        pytest.fail(
            "CMOS E2E requires an even PODONOS_E2E_FILE_COUNT because each "
            "CMOS item uploads one stimulus and one reference file."
        )
    return file_count // 2


def _add_cmos_file_pairs(
    etor,
    audio_path: Path,
    file_count: int,
    model_prefix: str,
    progress_every: int,
) -> None:
    pair_count = _cmos_pair_count(file_count)
    for index in range(pair_count):
        etor.add_files(
            file0=File(
                path=str(audio_path),
                model_tag=f"{model_prefix}_stimulus_{index % 5}",
                script="dev server CMOS e2e test stimulus",
                tags=["dev_e2e", "cmos", "stimulus"],
            ),
            file1=File(
                path=str(audio_path),
                model_tag=f"{model_prefix}_reference",
                script="dev server CMOS e2e test reference",
                tags=["dev_e2e", "cmos", "reference"],
                is_ref=True,
            ),
        )
        uploaded_count = (index + 1) * 2
        if uploaded_count % progress_every == 0 or index + 1 == pair_count:
            print(
                f"queued {uploaded_count}/{file_count} files "
                f"({index + 1}/{pair_count} CMOS pairs)"
            )


def _add_files_for_eval_type(
    etor,
    settings: DevServerSettings,
    model_prefix: str,
) -> None:
    if settings.eval_type == "CMOS":
        _add_cmos_file_pairs(
            etor,
            settings.audio_path,
            settings.file_count,
            model_prefix,
            settings.progress_every,
        )
        return

    _add_files(
        etor,
        settings.audio_path,
        settings.file_count,
        model_prefix,
        settings.progress_every,
    )


def test_dev_server_upload_verify_smoke_without_ledger(
    dev_server_settings: DevServerSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real dev-server smoke test: create evaluator, upload files, verify, process."""
    _skip_smoke_in_load_mode(dev_server_settings)

    # If the SDK accidentally creates the default ledger path when resume is off,
    # this isolated cwd makes the side effect easy to detect.
    monkeypatch.chdir(tmp_path)

    client = _new_client(dev_server_settings)
    etor = client.create_evaluator(
        name=_unique_name("sdk-dev-e2e-smoke"),
        desc="SDK dev-server E2E smoke test without upload ledger",
        type="NMOS",
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
        max_upload_workers=dev_server_settings.max_upload_workers,
        verify_batch_size=dev_server_settings.verify_batch_size,
        api_timeout=dev_server_settings.api_timeout,
        verify_timeout=dev_server_settings.verify_timeout,
        upload_timeout=dev_server_settings.upload_timeout,
    )

    evaluation_id = etor.get_evaluation_id()
    _add_files(
        etor,
        dev_server_settings.audio_path,
        dev_server_settings.file_count,
        "dev_smoke",
        dev_server_settings.progress_every,
    )

    result = etor.close()

    assert result == {"status": "ok"}
    assert evaluation_id
    assert not (tmp_path / ".podonos_upload_state.sqlite").exists()


def test_dev_server_upload_verify_with_opt_in_ledger(
    dev_server_settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    """Real dev-server E2E for opt-in ledger state through upload/verify."""
    _skip_smoke_in_load_mode(dev_server_settings)

    state_path = tmp_path / "podonos-e2e-upload-state.sqlite"
    client = _new_client(dev_server_settings)
    etor = client.create_evaluator(
        name=_unique_name("sdk-dev-e2e-ledger"),
        desc="SDK dev-server E2E smoke test with opt-in upload ledger",
        type="NMOS",
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
        max_upload_workers=dev_server_settings.max_upload_workers,
        verify_batch_size=1,
        api_timeout=dev_server_settings.api_timeout,
        verify_timeout=dev_server_settings.verify_timeout,
        upload_timeout=dev_server_settings.upload_timeout,
        resume_upload=True,
        upload_state_path=str(state_path),
    )

    evaluation_id = etor.get_evaluation_id()
    _add_files(
        etor,
        dev_server_settings.audio_path,
        dev_server_settings.file_count,
        "dev_ledger",
        dev_server_settings.progress_every,
    )

    result = etor.close()

    assert result == {"status": "ok"}
    assert state_path.exists()

    ledger = UploadLedger(str(state_path))
    counts = ledger.counts_by_status(evaluation_id)
    assert counts["verified"] == dev_server_settings.file_count
    assert sum(counts.values()) == dev_server_settings.file_count

    # Ledger/resume config must stay SDK-local and not leak into session/backend DTOs.
    config_dict = etor._eval_config.to_dict()  # type: ignore[attr-defined]
    create_dto = etor._eval_config.to_create_request_dto()  # type: ignore[attr-defined]
    assert "resume_upload" not in config_dict
    assert "upload_state_path" not in config_dict
    assert "resume_upload" not in create_dto
    assert "upload_state_path" not in create_dto


def test_dev_server_cmos_upload_verify_with_opt_in_ledger(
    dev_server_settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    """Real dev-server CMOS E2E for opt-in ledger state through upload/verify."""
    _skip_smoke_in_load_mode(dev_server_settings)
    _skip_unless_cmos_enabled()

    state_path = tmp_path / "podonos-e2e-cmos-upload-state.sqlite"
    client = _new_client(dev_server_settings)
    etor = client.create_evaluator(
        name=_unique_name("sdk-dev-e2e-cmos-ledger"),
        desc="SDK dev-server CMOS E2E smoke test with opt-in upload ledger",
        type="CMOS",
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
        max_upload_workers=dev_server_settings.max_upload_workers,
        verify_batch_size=dev_server_settings.verify_batch_size,
        api_timeout=dev_server_settings.api_timeout,
        verify_timeout=dev_server_settings.verify_timeout,
        upload_timeout=dev_server_settings.upload_timeout,
        resume_upload=True,
        upload_state_path=str(state_path),
    )

    evaluation_id = etor.get_evaluation_id()
    _add_cmos_file_pairs(
        etor,
        dev_server_settings.audio_path,
        dev_server_settings.file_count,
        "dev_cmos",
        dev_server_settings.progress_every,
    )

    result = etor.close()

    assert result == {"status": "ok"}
    assert state_path.exists()

    ledger = UploadLedger(str(state_path))
    counts = ledger.counts_by_status(evaluation_id)
    assert counts["verified"] == dev_server_settings.file_count
    assert sum(counts.values()) == dev_server_settings.file_count


def test_dev_server_upload_verify_large_file_count_with_opt_in_ledger(
    dev_server_settings: DevServerSettings,
    tmp_path: Path,
) -> None:
    """Real dev-server large-load E2E, intended for 5000-file verification."""
    if not dev_server_settings.load_mode:
        pytest.skip(
            "Set PODONOS_E2E_LOAD=1 and PODONOS_E2E_FILE_COUNT=5000 to run "
            "the large-load dev-server E2E test."
        )

    state_path = tmp_path / "podonos-e2e-large-upload-state.sqlite"
    client = _new_client(dev_server_settings)
    etor = client.create_evaluator(
        name=_unique_name(
            f"sdk-dev-e2e-{dev_server_settings.eval_type.lower()}-load-"
            f"{dev_server_settings.file_count}"
        ),
        desc=(
            f"SDK dev-server {dev_server_settings.eval_type} large-load E2E "
            "with opt-in upload ledger "
            f"({dev_server_settings.file_count} files)"
        ),
        type=dev_server_settings.eval_type,
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
        max_upload_workers=dev_server_settings.max_upload_workers,
        verify_batch_size=dev_server_settings.verify_batch_size,
        api_timeout=dev_server_settings.api_timeout,
        verify_timeout=dev_server_settings.verify_timeout,
        upload_timeout=dev_server_settings.upload_timeout,
        resume_upload=True,
        upload_state_path=str(state_path),
    )

    evaluation_id = etor.get_evaluation_id()
    print(
        "large-load e2e settings: "
        f"evaluation_id={evaluation_id}, "
        f"eval_type={dev_server_settings.eval_type}, "
        f"file_count={dev_server_settings.file_count}, "
        f"max_upload_workers={dev_server_settings.max_upload_workers}, "
        f"verify_batch_size={dev_server_settings.verify_batch_size}, "
        f"base_url={dev_server_settings.base_url}"
    )
    _add_files_for_eval_type(
        etor,
        dev_server_settings,
        "dev_load",
    )

    result = etor.close()

    assert result == {"status": "ok"}
    assert state_path.exists()

    ledger = UploadLedger(str(state_path))
    counts = ledger.counts_by_status(evaluation_id)
    assert counts["verified"] == dev_server_settings.file_count
    assert sum(counts.values()) == dev_server_settings.file_count
