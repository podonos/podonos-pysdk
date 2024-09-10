"""
Runs a single evaluation.

Example:
    python single_eval_test.py --api_key=<MY_API_KEY> --base_url=<BASE_URL>
"""

import argparse
import podonos
from podonos import *
from podonos.core.base import *
import sys


def main():
    parser = argparse.ArgumentParser(description="Run a single evaluation test.")
    parser.add_argument("--api_key", required=True, help="API Key")
    parser.add_argument("--base_url", required=False, help="Base URL for the backend APIs.")
    args = parser.parse_args()

    log.info(f"Python version: {sys.version}")
    log.info(f"Podonos package version: {podonos.__version__}")
    log.debug(f"Base URL: {args.base_url}")
    client = podonos.init(api_key=args.api_key, api_url=args.base_url)

    # Default evaluator.
    etor = client.create_evaluator(
        name='Naturalness test',
        desc='Naturalness test',
        lan='en-gb',
        type='NMOS',
        num_eval=10,
        use_annotation=True
    )
    evaluation_id = etor.get_evaluation_id()
    log.info(f"Evaluation id: {evaluation_id}")
    etor.add_file(File(path=f"speech_two_ch1.wav", model_tag='my_new_model1', script='hello world'))
    etor.add_file(File(path=f"speech_two_ch2.wav", model_tag='my_new_model2', script='hello world wow'))
    etor.close()


if __name__ == "__main__":
    main()
