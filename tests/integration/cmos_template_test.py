"""
End-to-End Test for CMOS Template Support

This script tests the CMOS (Comparative Mean Opinion Score) template support
in the podonos SDK. It demonstrates:

1. CustomType enum values verification (no API call)
2. Invalid custom_type error handling
3. create_from_template_json() with SINGLE_REF custom_type (string)
4. create_from_template_json() with CustomType.SINGLE_REF enum
5. Multiple models comparison against a single reference

Example:
    python cmos_template_test.py --api_key=<MY_API_KEY>
    python cmos_template_test.py --api_key=<MY_API_KEY> --base_url=<BASE_URL>
    python cmos_template_test.py --api_key=<MY_API_KEY> --reference=ref.wav --target=target.wav
"""

import argparse
import os
import sys

import podonos
from podonos.common.enum import CustomType
from podonos.core.base import log
from podonos.core.file import File

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"
_TEMPLATE_JSON_PATH = os.path.join(os.path.dirname(__file__), "cmos_template.json")


def test_custom_type_enum_values():
    """Test 1: Verify CustomType enum values (no API call)"""
    log.info("=" * 60)
    log.info("Test 1: CustomType enum values")
    log.info("=" * 60)

    log.info(f"CustomType.SINGLE = '{CustomType.SINGLE.value}'")
    log.info(f"CustomType.DOUBLE = '{CustomType.DOUBLE.value}'")
    log.info(f"CustomType.SINGLE_REF = '{CustomType.SINGLE_REF.value}'")
    log.info(f"CustomType.RANKING = '{CustomType.RANKING.value}'")
    log.info(f"All values: {CustomType.values()}")
    log.info(
        f"CustomType.from_value('SINGLE_REF') = {CustomType.from_value('SINGLE_REF')}"
    )

    return True


def test_invalid_custom_type(client):
    """Test 2: Verify invalid custom_type raises error"""
    log.info("=" * 60)
    log.info("Test 2: Invalid custom_type error handling")
    log.info("=" * 60)

    try:
        client.create_evaluator_from_template_json(
            json={"questions": []},
            name="Invalid Test",
            custom_type="INVALID_TYPE",
        )
        log.error("  - ERROR: Should have raised ValueError")
        return False
    except ValueError as e:
        log.info(f"  - Correctly raised ValueError: {e}")
        return True


def test_create_from_template_json_with_string(client, reference_audio, target_audio):
    """Test 3: create_from_template_json with custom_type as string"""
    log.info("=" * 60)
    log.info("Test 3: create_from_template_json (custom_type='SINGLE_REF')")
    log.info("=" * 60)

    evaluator = client.create_evaluator_from_template_json(
        json_file=_TEMPLATE_JSON_PATH,
        name="CMOS Test - String Type",
        custom_type="SINGLE_REF",
        desc="Testing CMOS with SINGLE_REF string value",
        num_eval=1,
        auto_start=False,
    )

    log.info(f"Evaluator created successfully!")
    log.info(f"  - Evaluation ID: {evaluator.get_evaluation_id()}")
    log.info(f"  - Eval Type: {evaluator._eval_config.eval_type}")
    log.info(f"  - Supported Types: {evaluator._supported_eval_types}")

    if reference_audio and target_audio:
        if os.path.exists(reference_audio) and os.path.exists(target_audio):
            evaluator.add_files(
                file0=File(path=target_audio, tags=["tts"], model_tag="tts_model_v1"),
                file1=File(
                    path=reference_audio,
                    tags=["human"],
                    is_ref=True,
                    model_tag="human_reference",
                ),
            )
            log.info(f"  - Files added successfully")
        else:
            log.warning(f"  - Audio files not found, skipping file upload")

    evaluator.close()
    log.info(f"  - Evaluator closed")

    return True


def test_create_from_template_json_with_enum(client, reference_audio, target_audio):
    """Test 4: create_from_template_json with CustomType enum"""
    log.info("=" * 60)
    log.info("Test 4: create_from_template_json (custom_type=CustomType.SINGLE_REF)")
    log.info("=" * 60)

    template_json = {
        "questions": [
            {
                "type": "SCORED",
                "question": "Rate the quality of the synthesized audio compared to the reference.",
                "options": [
                    {"label_text": "Much worse", "value": 1},
                    {"label_text": "Worse", "value": 2},
                    {"label_text": "Same", "value": 3},
                    {"label_text": "Better", "value": 4},
                    {"label_text": "Much better", "value": 5},
                ],
            }
        ]
    }

    evaluator = client.create_evaluator_from_template_json(
        json=template_json,
        name="CMOS Test - Enum Type",
        custom_type=CustomType.SINGLE_REF,
        desc="Testing CMOS with CustomType.SINGLE_REF enum",
        num_eval=1,
        auto_start=False,
    )

    log.info(f"Evaluator created successfully!")
    log.info(f"  - Evaluation ID: {evaluator.get_evaluation_id()}")
    log.info(f"  - Eval Type: {evaluator._eval_config.eval_type}")
    log.info(f"  - Supported Types: {evaluator._supported_eval_types}")

    if reference_audio and target_audio:
        if os.path.exists(reference_audio) and os.path.exists(target_audio):
            evaluator.add_files(
                file0=File(path=target_audio, tags=["tts"], model_tag="tts_model_v1"),
                file1=File(
                    path=reference_audio,
                    tags=["human"],
                    is_ref=True,
                    model_tag="human_reference",
                ),
            )
            log.info(f"  - Files added successfully")
        else:
            log.warning(f"  - Audio files not found, skipping file upload")

    evaluator.close()
    log.info(f"  - Evaluator closed")

    return True


def test_multiple_models_vs_reference(client, reference_audio, target_audio):
    """Test 5: Compare multiple models (A, B) against a single reference"""
    log.info("=" * 60)
    log.info("Test 5: Multiple models vs reference (ref vs A, ref vs B)")
    log.info("=" * 60)

    template_json = {
        "questions": [
            {
                "type": "SCORED",
                "question": "Rate the quality of the synthesized audio compared to the reference.",
                "options": [
                    {"label_text": "Much worse", "value": 1},
                    {"label_text": "Worse", "value": 2},
                    {"label_text": "Same", "value": 3},
                    {"label_text": "Better", "value": 4},
                    {"label_text": "Much better", "value": 5},
                ],
            }
        ]
    }

    evaluator = client.create_evaluator_from_template_json(
        json=template_json,
        name="CMOS Test - Multiple Models",
        custom_type=CustomType.SINGLE_REF,
        desc="Testing multiple TTS models against a single reference",
        num_eval=1,
        auto_start=False,
    )

    log.info(f"Evaluator created successfully!")
    log.info(f"  - Evaluation ID: {evaluator.get_evaluation_id()}")

    models = ["model_a", "model_b", "model_c"]
    files_added = 0

    if reference_audio and target_audio:
        if os.path.exists(reference_audio) and os.path.exists(target_audio):
            for model in models:
                evaluator.add_files(
                    file0=File(
                        path=target_audio,
                        tags=["tts", model],
                        model_tag=model,
                    ),
                    file1=File(
                        path=reference_audio,
                        tags=["human"],
                        is_ref=True,
                        model_tag="human_reference",
                    ),
                )
                log.info(f"  - Added pair: reference vs {model}")
                files_added += 1
        else:
            log.warning(f"  - Audio files not found, skipping file upload")

    evaluator.close()
    log.info(f"  - Evaluator closed with {files_added} model comparisons")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run CMOS template support integration tests."
    )
    parser.add_argument("--api_key", required=True, help="API key string.")
    parser.add_argument(
        "--base_url",
        required=False,
        default=_PODONOS_API_BASE_URL,
        help="Base URL for the backend APIs.",
    )
    parser.add_argument(
        "--reference",
        required=False,
        default=None,
        help="Path to reference audio file.",
    )
    parser.add_argument(
        "--target",
        required=False,
        default=None,
        help="Path to target/synthesized audio file.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip tests that require API calls.",
    )
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.info(f"Base URL: {args.base_url}")

    results = []

    # Test 1: CustomType enum (no API call)
    results.append(("CustomType enum values", test_custom_type_enum_values()))

    if not args.skip_api:
        client = podonos.init(api_key=args.api_key, api_url=args.base_url)

        # Test 2: Invalid custom_type
        results.append(("Invalid custom_type", test_invalid_custom_type(client)))

        # Test 3: create_from_template_json with string
        results.append(
            (
                "create_from_template_json (string)",
                test_create_from_template_json_with_string(
                    client, args.reference, args.target
                ),
            )
        )

        # Test 4: create_from_template_json with enum
        results.append(
            (
                "create_from_template_json (enum)",
                test_create_from_template_json_with_enum(
                    client, args.reference, args.target
                ),
            )
        )

        # Test 5: Multiple models vs reference
        results.append(
            (
                "multiple models vs reference",
                test_multiple_models_vs_reference(client, args.reference, args.target),
            )
        )

    log.info("=" * 60)
    log.info("Test Results Summary")
    log.info("=" * 60)
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        log.info(f"  [{status}] {name}")

    all_passed = all(passed for _, passed in results)
    log.info("All tests passed!" if all_passed else "Some tests failed!")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
