"""
Runs an upload test with multiple file uploads between the SDK and the backend APIs.

Keep in mind that depending on the configuration, you may produce a direct impact on the dev or prod servers.

Example:
    python upload_manager_load_test.py --api_key=<MY_API_KEY>

"""

import argparse
import podonos
from podonos import *
from podonos.core.base import *
import sys
import time

_PODONOS_API_BASE_URL = "https://dev.podonosapi.com"


def main():
    parser = argparse.ArgumentParser(description="Run an integration test for SDK and backend APIs.")
    parser.add_argument("--api_key", required=True, help="API key string.")
    parser.add_argument("--base_url", required=False, default=_PODONOS_API_BASE_URL, help="Base URL for the backend APIs.")
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.debug(f"API Key: {args.api_key}")
    log.debug(f"Base URL: {args.base_url}")
    client = podonos.init(api_key=args.api_key, api_url=args.base_url)

    num_workers = 10
    etor = client.create_evaluator(name=f"upload test with {num_workers} upload workers")
    evaluation_id = etor.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id}")
    start_upload = time.time()
    for i in range(100):
        etor.add_file(File(path=f"tests/speech_two_ch1.wav"))
        etor.add_file(File(path=f"tests/speech_two_ch2.wav"))
    etor.close()
    end_upload = time.time()
    log.info(f"Time elapsed with {num_workers} workers: {end_upload - start_upload:.2f} seconds")


if __name__ == "__main__":
    main()
