"""
Integration tests for upload verification system.

Usage:
    pytest tests/integration/test_upload_verification.py -v --api_key=<KEY> --base_url=<URL>

    python tests/integration/test_upload_verification.py --api_key=<KEY> --base_url=<URL>
"""

import argparse
import os
import sys
import tempfile
import wave
import struct
import math

import podonos
from podonos import File
from podonos.core.base import log
from podonos.errors import UploadRetryExhaustedError


def create_test_wav(
    path: str, duration_seconds: float = 1.0, sample_rate: int = 16000
) -> None:
    num_samples = int(sample_rate * duration_seconds)
    frequency = 440

    with wave.open(path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for i in range(num_samples):
            value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav_file.writeframes(struct.pack("<h", value))


def test_verification_with_corrupted_md5(
    api_key: str, base_url: str | None = None
) -> bool:
    """
    Corrupts MD5 after upload to simulate network corruption.
    Expects UploadRetryExhaustedError since verification will always fail.
    """
    log.info("=" * 60)
    log.info("TEST: Verification with corrupted MD5")
    log.info("=" * 60)

    init_kwargs = {"api_key": api_key}
    if base_url:
        init_kwargs["api_url"] = base_url
    client = podonos.init(**init_kwargs)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        test_file_path = f.name
    create_test_wav(test_file_path)

    try:
        etor = client.create_evaluator(
            name="Verification Test - Corrupted MD5",
            desc="Testing verification failure with corrupted MD5",
            lan="en-us",
            type="NMOS",
            num_eval=1,
        )
        evaluation_id = etor.get_evaluation_id()
        log.info(f"Created evaluation: {evaluation_id}")

        etor.add_file(File(path=test_file_path, model_tag="test_model", script="test"))
        log.info("File added and upload started")

        log.info("Waiting for upload to complete...")
        if etor._upload_manager:
            etor._upload_manager.wait_and_close()
            etor._upload_manager = None

        log.info("Corrupting MD5 hash to simulate network corruption...")
        for group in etor._ordered_file_groups:
            for audio in group.audios:
                original_md5 = audio._content_md5
                audio._content_md5 = "AAAAAAAAAAAAAAAAAAAAAA=="
                log.info(f"  {audio.path}: {original_md5} -> {audio._content_md5}")

        log.info("Setting MAX_UPLOAD_RETRIES=0 to fail immediately without retry...")
        import podonos.core.evaluator as evaluator_module
        from podonos.core.upload_manager import UploadManager

        original_max_retries = evaluator_module.MAX_UPLOAD_RETRIES
        evaluator_module.MAX_UPLOAD_RETRIES = 0

        log.info("Calling close() - expecting verification failure...")
        try:
            etor._upload_manager = UploadManager(
                evaluation_service=etor._evaluation_service,
                max_workers=1,
            )

            etor.close()
            log.error(
                "TEST FAILED: Expected UploadRetryExhaustedError but close() succeeded"
            )
            return False

        except UploadRetryExhaustedError as e:
            log.info(f"TEST PASSED: Got expected error: {type(e).__name__}")
            log.info(f"  Message: {e}")
            log.info(f"  Retry count: {e.retry_count}")
            log.info(f"  Max retries: {e.max_retries}")
            log.info(f"  Failed files: {len(e.failures)}")
            for failure in e.failures:
                log.info(
                    f"    - {failure.original_name}: {failure.error_code} - {failure.message}"
                )
            return True

        except Exception as e:
            log.error(f"TEST FAILED: Got unexpected error: {type(e).__name__}: {e}")
            return False

        finally:
            evaluator_module.MAX_UPLOAD_RETRIES = original_max_retries

    finally:
        if test_file_path and os.path.exists(test_file_path):
            os.unlink(test_file_path)


def test_verification_success(api_key: str, base_url: str | None = None) -> bool:
    """Sanity check: verification succeeds for properly uploaded files."""
    log.info("=" * 60)
    log.info("TEST: Verification success (normal flow)")
    log.info("=" * 60)

    init_kwargs = {"api_key": api_key}
    if base_url:
        init_kwargs["api_url"] = base_url
    client = podonos.init(**init_kwargs)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        test_file_path = f.name
    create_test_wav(test_file_path)

    try:
        etor = client.create_evaluator(
            name="Verification Test - Normal Flow",
            desc="Testing verification success with normal upload",
            lan="en-us",
            type="NMOS",
            num_eval=1,
        )
        evaluation_id = etor.get_evaluation_id()
        log.info(f"Created evaluation: {evaluation_id}")

        etor.add_file(File(path=test_file_path, model_tag="test_model", script="test"))
        log.info("File added")

        try:
            etor.close()
            log.info("TEST PASSED: close() succeeded as expected")
            return True
        except Exception as e:
            log.error(
                f"TEST FAILED: Unexpected error during close(): {type(e).__name__}: {e}"
            )
            return False

    finally:
        if os.path.exists(test_file_path):
            os.unlink(test_file_path)


def main():
    parser = argparse.ArgumentParser(
        description="Run upload verification integration tests."
    )
    parser.add_argument("--api_key", required=True, help="API Key")
    parser.add_argument(
        "--base_url", required=False, help="Base URL for the backend APIs."
    )
    parser.add_argument(
        "--test",
        choices=["all", "success", "corrupted"],
        default="all",
        help="Which test to run",
    )
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.info(f"Base URL: {args.base_url}")

    results = []

    if args.test in ("all", "success"):
        results.append(
            ("success", test_verification_success(args.api_key, args.base_url))
        )

    if args.test in ("all", "corrupted"):
        results.append(
            (
                "corrupted",
                test_verification_with_corrupted_md5(args.api_key, args.base_url),
            )
        )

    log.info("=" * 60)
    log.info("TEST SUMMARY")
    log.info("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        log.info(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        log.info("All tests passed!")
        sys.exit(0)
    else:
        log.error("Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
