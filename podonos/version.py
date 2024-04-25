"""
Package version related functions
"""


import importlib.metadata
import logging
from packaging.version import Version
import requests
from typing import Tuple

from podonos.constant import bcolors

# For logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def get_versions(api_url: str) -> Tuple[str, str, str]:
    """Gets the minimum, recommended, and latest versions of this package.

    Returns:
        {min, recommended, latest} versions
    """
    response = requests.get(f'{api_url}/version/sdk')
    if response.status_code != 200:
        raise requests.exceptions.HTTPError
    version_json = response.json()
    min_version = version_json.get('minimum')
    recommended_version = version_json.get('recommended')
    latest_version = version_json.get('latest')
    return min_version, recommended_version, latest_version


def check_min_required_version(api_url: str) -> bool:
    """Checks if this package is the same or higher than the minimum required version.

    Returns:
        True if the current package version is the same or higher than the minimum required version.
        False with printing a warning message
    """
    min_version, recommended_version, latest_version = get_versions(api_url)
    current_version = importlib.metadata.version("podonos")
    log.debug(f'current package version: {current_version}')

    if Version(current_version) >= Version(recommended_version):
        # Great!
        return True

    if Version(current_version) >= Version(min_version):
        # This version is higher than the minimum required version, but less than the recommended
        # version. Gently recommend to upgrade.
        print(bcolors.WARN + f"The current podonos package version is {current_version} "
              f"while a newer version {latest_version} is available" + bcolors.ENDC + "\n" +
              bcolors.BOLD + "Please upgrade" + bcolors.ENDC + " by "
              f"'pip install podonos --upgrade'")
        return True

    # This version is lower than the minimum required version. Cannot proceed.
    print(bcolors.FAIL + f"The current podonos package version is {current_version} "
                         f"while the minimum supported version is {min_version}" + bcolors.ENDC + "\n" +
          bcolors.BOLD + "Please upgrade" + bcolors.ENDC + f" by 'pip install podonos --upgrade'")
    return False
