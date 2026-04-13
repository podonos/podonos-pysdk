"""
E2E test: RANKING evaluation with script_tags.

Verifies that script_tags set via the SDK are correctly sent to the backend
through the PUT evaluation-files API.

Example:
    python tests/integration/ranking_script_tags_test.py --api_key=<KEY>
    python tests/integration/ranking_script_tags_test.py --api_key=<KEY> --base_url=https://dev.podonosapi.com
"""

import argparse
import sys
from datetime import datetime

import podonos
from podonos import *
from podonos.core.base import *

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"


def main():
    parser = argparse.ArgumentParser(description="E2E test: RANKING with script_tags")
    parser.add_argument("--api_key", required=True, help="API key string.")
    parser.add_argument(
        "--base_url",
        required=False,
        default=_PODONOS_API_BASE_URL,
        help="Base URL for the backend APIs.",
    )
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.info(f"Base URL: {args.base_url}")

    client = podonos.init(api_key=args.api_key, api_url=args.base_url)

    name_prefix = datetime.today().strftime("%Y%m%d%H%M%S")

    # --- Test 1: RANKING with script_tags ---
    log.info("=== Test 1: RANKING with script_tags ===")
    etor = client.create_evaluator(
        name=f"{name_prefix}_ranking_script_tags",
        desc="E2E test for script_tags support in RANKING evaluation",
        type="RANKING",
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
    )
    evaluation_id = etor.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id}")

    # Group 1: "address" script tag
    etor.add_ranking_set([
        File(
            path="tests/core/speech_two_ch1.wav",
            model_tag="ModelA",
            tags=["english"],
            script_tags=["address"],
            script="Please tell me your address.",
        ),
        File(
            path="tests/core/speech_two_ch2.wav",
            model_tag="ModelB",
            tags=["english"],
            script_tags=["address"],
            script="Please tell me your address.",
        ),
    ])
    log.info("Group 1 added (script_tags=['address'])")

    # Group 2: "greeting" script tag
    etor.add_ranking_set([
        File(
            path="tests/core/speech_two_ch1.wav",
            model_tag="ModelA",
            tags=["english"],
            script_tags=["greeting"],
            script="Hello, how are you?",
        ),
        File(
            path="tests/core/speech_two_ch2.wav",
            model_tag="ModelB",
            tags=["english"],
            script_tags=["greeting"],
            script="Hello, how are you?",
        ),
    ])
    log.info("Group 2 added (script_tags=['greeting'])")

    # Group 3: no script_tags (backward compatibility)
    etor.add_ranking_set([
        File(
            path="tests/core/speech_two_ch1.wav",
            model_tag="ModelA",
            tags=["english"],
            script="Good morning.",
        ),
        File(
            path="tests/core/speech_two_ch2.wav",
            model_tag="ModelB",
            tags=["english"],
            script="Good morning.",
        ),
    ])
    log.info("Group 3 added (no script_tags, backward compat)")

    etor.close()
    log.info(f"RANKING evaluation closed successfully. ID: {evaluation_id}")

    # --- Test 2: RANKING with multiple script_tags per file ---
    log.info("=== Test 2: RANKING with multiple script_tags ===")
    etor2 = client.create_evaluator(
        name=f"{name_prefix}_ranking_multi_script_tags",
        desc="E2E test for multiple script_tags",
        type="RANKING",
        lan="en-us",
        num_eval=1,
        due_hours=12,
        auto_start=False,
    )
    evaluation_id2 = etor2.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id2}")

    etor2.add_ranking_set([
        File(
            path="tests/core/speech_two_ch1.wav",
            model_tag="ModelA",
            tags=["english", "male"],
            script_tags=["address", "formal"],
        ),
        File(
            path="tests/core/speech_two_ch2.wav",
            model_tag="ModelB",
            tags=["english", "male"],
            script_tags=["address", "casual"],
        ),
    ])
    log.info("Group added with multiple + different script_tags per file")

    etor2.close()
    log.info(f"RANKING evaluation closed successfully. ID: {evaluation_id2}")

    log.info("=== All E2E tests passed ===")


if __name__ == "__main__":
    main()
