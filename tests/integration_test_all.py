"""
Runs an integration test between the SDK and the backend APIs.
For a completeness, you may run this test on multiple python environments.

Keep in mind that depending on the configuration, you may produce a direct impact on the dev or prod servers.

Example:
    python integration_test_all.py --api_key=<MY_API_KEY>
    python integration_test_all.py --api_key=<MY_API_KEY> --base_url=<BASE_URL>

"""

import argparse
from datetime import datetime
import podonos
from podonos import *
from podonos.core.base import *
import random
import sys

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"


def main():
    parser = argparse.ArgumentParser(description="Run an integration test for SDK and backend APIs.")
    parser.add_argument("--api_key", required=True, help="API key string.")
    parser.add_argument("--random", required=False, default=False, help="Randomly select configurations.")
    parser.add_argument("--base_url", required=False, default=_PODONOS_API_BASE_URL, help="Base URL for the backend APIs.")
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.debug(f"API Key: {args.api_key}")
    log.debug(f"Base URL: {args.base_url}")
    client = podonos.init(api_key=args.api_key, api_url=args.base_url)

    # Default evaluator.
    etor = client.create_evaluator()
    evaluation_id = etor.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id}")
    etor.add_file(File(path=f"tests/speech_two_ch1.wav"))
    etor.add_file(File(path=f"tests/speech_two_ch2.wav"))
    etor.close()

    #
    name_prefix = datetime.today().strftime("%Y%m%d%H%M%S")
    type_all = ["NMOS", "P808"]
    lan_all = ["en-us", "en-gb", "en-au", "en-ca", "ko-kr", "audio"]
    if args.random:
        test_type = random.choice(type_all)
        test_lan = random.choice(lan_all)
        test_num_eval = random.randint(1, 50)
        test_due_hours = random.randint(12, 120)
        test_auto_start = random.choice([True, False])
    else:
        test_type = type_all[0]
        test_lan = lan_all[0]
        test_num_eval = 10
        test_due_hours = 12
        test_auto_start = False
    etor = client.create_evaluator(
        name=f"{name_prefix}_test_name",
        desc=f"{name_prefix}_desc",
        type=test_type,
        lan=test_lan,
        num_eval=test_num_eval,
        due_hours=test_due_hours,
        auto_start=test_auto_start,
    )
    evaluation_id = etor.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id}")
    etor.add_file(File(path=f"tests/speech_two_ch1.wav"))
    etor.add_file(File(path=f"tests/speech_two_ch2.wav"))
    etor.close()

    stats = client.get_stats_dict_by_id(evaluation_id)
    log.debug(stats)
    client.download_stats_csv_by_id(evaluation_id, f"./eval_stats_{evaluation_id}.csv")

    log.info(f"Evaluation id list")
    evaluations = client.get_evaluation_list()
    for evaluation in evaluations:
        eval_id = evaluation["id"]
        log.info(f"ID: {eval_id}")


if __name__ == "__main__":
    main()
