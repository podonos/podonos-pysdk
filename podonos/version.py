"""
Package version related functions
"""


import importlib.metadata
import logging
from packaging.version import Version
import requests

from podonos.constant import bcolors

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def get_min_required_version(api_url):
    """Gets the minimum required version of this package.

    Returns:
        The minimum required version strong.
    """
    response = requests.get(f'{api_url}/version/min-required')
    if response.status_code != 200:
        raise requests.exceptions.HTTPError
    required_version = response.text.replace('"', '')
    return required_version


def check_min_required_version(required_version) -> bool:
    """Checks if this package is the same or higher than the minimum required version.

    Returns:
        True if the current package version is the same or higher than the minimum required version.
        False with printing a warning message
    """
    current_version = importlib.metadata.version("podonos")
    log.debug(f'current package version: {current_version}')
    if Version(current_version) >= Version(required_version):
        return True
    print(bcolors.WARN + f"The minimum podonos package version is {required_version} while " +
          f"the current version is {current_version}." + bcolors.ENDC + "\n"
          "Please upgrade by 'pip install podonos --upgrade'")
    return False
