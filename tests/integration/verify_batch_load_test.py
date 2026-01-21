"""
Integration test for verify_files batch processing with large file counts.

This test validates that the batch processing fix for verify_files works correctly
when uploading a large number of files (e.g., 1900+ files) that previously caused
30-second timeout errors.

Usage:
    python tests/integration/verify_batch_load_test.py --api_key=<KEY> [--base_url=<URL>] [--file_count=1000] [--verify_batch_size=500]

Example:
    # Test with 1000 files (default)
    python tests/integration/verify_batch_load_test.py --api_key=<KEY>

    # Test with 1900 files (reproduces customer issue)
    python tests/integration/verify_batch_load_test.py --api_key=<KEY> --file_count=1900

    # Test with custom backend URL
    python tests/integration/verify_batch_load_test.py --api_key=<KEY> --base_url=https://dev.podonosapi.com

    # Test with custom verify batch size
    python tests/integration/verify_batch_load_test.py --api_key=<KEY> --file_count=1000 --verify_batch_size=200
"""

import argparse
import math
import os
import struct
import sys
import tempfile
import time
import wave
from typing import List

import podonos
from podonos import File
from podonos.core.base import log

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"


def create_test_wav(
    path: str, duration_seconds: float = 0.5, sample_rate: int = 16000
) -> None:
    """Create a test WAV file with a simple sine wave."""
    num_samples = int(sample_rate * duration_seconds)
    frequency = 440  # A4 note

    with wave.open(path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        for i in range(num_samples):
            value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav_file.writeframes(struct.pack("<h", value))


def run_large_file_count_verification(
    api_key: str,
    base_url: str | None = None,
    file_count: int = 1000,
    max_upload_workers: int = 10,
    verify_batch_size: int = 500,
) -> bool:
    """
    Test that verify_files batch processing works correctly with large file counts.

    This test:
    1. Creates a large number of test WAV files
    2. Uploads them via the SDK
    3. Verifies that the batch processing doesn't timeout

    The fix ensures verify_files is called in batches (default 500 files) instead of
    sending all files at once, which caused 30-second timeout errors with 1900+ files.

    Args:
        api_key: Podonos API key
        base_url: Optional backend URL override
        file_count: Number of files to upload (default 1000)
        max_upload_workers: Number of parallel upload workers
        verify_batch_size: Batch size for file verification API calls (default 500)

    Returns:
        True if test passed, False otherwise
    """
    log.info("=" * 70)
    log.info(f"TEST: Large file count verification ({file_count} files)")
    log.info("=" * 70)
    log.info(f"  File count: {file_count}")
    log.info(f"  Verify batch size: {verify_batch_size}")
    log.info(
        f"  Expected verify batches: {(file_count + verify_batch_size - 1) // verify_batch_size}"
    )
    log.info(f"  Max upload workers: {max_upload_workers}")

    # Initialize client
    init_kwargs = {"api_key": api_key}
    if base_url:
        init_kwargs["api_url"] = base_url
    client = podonos.init(**init_kwargs)

    # Create temporary test files
    temp_dir = tempfile.mkdtemp(prefix="podonos_batch_test_")
    test_files: List[str] = []

    try:
        # Create test WAV files
        log.info(f"Creating {file_count} test WAV files...")
        start_create = time.time()
        for i in range(file_count):
            file_path = os.path.join(temp_dir, f"test_audio_{i:05d}.wav")
            create_test_wav(file_path, duration_seconds=0.5)
            test_files.append(file_path)
            if (i + 1) % 100 == 0:
                log.info(f"  Created {i + 1}/{file_count} files...")
        end_create = time.time()
        log.info(f"Created {file_count} files in {end_create - start_create:.2f}s")

        # Create evaluator
        etor = client.create_evaluator(
            name=f"Batch Verify Load Test ({file_count} files)",
            desc=f"Testing verify_files batch processing with {file_count} files",
            lan="en-us",
            type="NMOS",
            num_eval=1,
            max_upload_workers=max_upload_workers,
            verify_batch_size=verify_batch_size,
        )
        evaluation_id = etor.get_evaluation_id()
        log.info(f"Created evaluation: {evaluation_id}")

        # Add all files
        log.info(f"Adding {file_count} files to evaluation...")
        start_add = time.time()
        for i, file_path in enumerate(test_files):
            etor.add_file(File(path=file_path, model_tag=f"model_{i % 5}"))
            if (i + 1) % 100 == 0:
                log.info(f"  Added {i + 1}/{file_count} files...")
        end_add = time.time()
        log.info(f"Added {file_count} files in {end_add - start_add:.2f}s")

        # Close evaluator (this triggers upload completion and verification)
        log.info("Closing evaluator (upload + verification)...")
        log.info(f"  This will verify files in batches of {verify_batch_size}...")
        start_close = time.time()

        try:
            result = etor.close()
            end_close = time.time()

            log.info(f"Close completed in {end_close - start_close:.2f}s")
            log.info(f"Result: {result}")

            if result.get("status") == "ok":
                log.info("=" * 70)
                log.info("TEST PASSED: All files uploaded and verified successfully!")
                log.info("=" * 70)
                log.info(f"  Total time: {end_close - start_create:.2f}s")
                log.info(f"  File creation: {end_create - start_create:.2f}s")
                log.info(f"  File adding: {end_add - start_add:.2f}s")
                log.info(f"  Upload + verify: {end_close - start_close:.2f}s")
                return True
            else:
                log.error(f"TEST FAILED: Unexpected result: {result}")
                return False

        except Exception as e:
            end_close = time.time()
            log.error(
                f"TEST FAILED: Error during close() after {end_close - start_close:.2f}s"
            )
            log.error(f"  Error type: {type(e).__name__}")
            log.error(f"  Error message: {e}")

            # Check if it's a timeout error (the bug we're fixing)
            error_str = str(e).lower()
            if "timeout" in error_str or "timed out" in error_str:
                log.error("  This appears to be a TIMEOUT error!")
                log.error("  The batch processing fix may not be working correctly.")
            return False

    finally:
        # Cleanup test files
        log.info("Cleaning up test files...")
        for file_path in test_files:
            try:
                os.unlink(file_path)
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass
        log.info("Cleanup complete.")


def run_incremental_file_counts(
    api_key: str,
    base_url: str | None = None,
) -> bool:
    """
    Test with incrementally larger file counts to find breaking point.

    Tests with: 100, 500, 600, 1000 files
    """
    log.info("=" * 70)
    log.info("TEST: Incremental file count verification")
    log.info("=" * 70)

    test_counts = [100, 500, 600, 1000]
    results = []

    for count in test_counts:
        log.info(f"\n--- Testing with {count} files ---")
        passed = run_large_file_count_verification(
            api_key=api_key,
            base_url=base_url,
            file_count=count,
            max_upload_workers=10,
        )
        results.append((count, passed))

        if not passed:
            log.error(f"Failed at {count} files, stopping incremental test")
            break

    log.info("\n" + "=" * 70)
    log.info("INCREMENTAL TEST SUMMARY")
    log.info("=" * 70)
    all_passed = True
    for count, passed in results:
        status = "PASSED" if passed else "FAILED"
        log.info(f"  {count} files: {status}")
        if not passed:
            all_passed = False

    return all_passed


def main():
    parser = argparse.ArgumentParser(
        description="Run verify_files batch processing load test.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test with 1000 files (default)
    python verify_batch_load_test.py --api_key=<KEY>

    # Test with 1900 files (customer issue scenario)
    python verify_batch_load_test.py --api_key=<KEY> --file_count=1900

    # Run incremental test (100, 500, 600, 1000 files)
    python verify_batch_load_test.py --api_key=<KEY> --test=incremental
        """,
    )
    parser.add_argument("--api_key", required=True, help="Podonos API key")
    parser.add_argument(
        "--base_url",
        required=False,
        default=_PODONOS_API_BASE_URL,
        help=f"Base URL for the backend APIs (default: {_PODONOS_API_BASE_URL})",
    )
    parser.add_argument(
        "--file_count",
        type=int,
        default=1000,
        help="Number of files to upload (default: 1000)",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=10,
        help="Number of parallel upload workers (default: 10)",
    )
    parser.add_argument(
        "--verify_batch_size",
        type=int,
        default=500,
        help="Batch size for file verification API calls (default: 500, range: 1-1000)",
    )
    parser.add_argument(
        "--test",
        choices=["single", "incremental"],
        default="single",
        help="Test mode: single (default) or incremental",
    )
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.info(f"Base URL: {args.base_url}")
    log.info(f"Test mode: {args.test}")
    log.info(f"Verify batch size: {args.verify_batch_size}")

    if args.test == "incremental":
        passed = run_incremental_file_counts(
            api_key=args.api_key,
            base_url=args.base_url,
        )
    else:
        passed = run_large_file_count_verification(
            api_key=args.api_key,
            base_url=args.base_url,
            file_count=args.file_count,
            max_upload_workers=args.max_workers,
            verify_batch_size=args.verify_batch_size,
        )

    if passed:
        log.info("\n✅ TEST PASSED")
        sys.exit(0)
    else:
        log.error("\n❌ TEST FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
