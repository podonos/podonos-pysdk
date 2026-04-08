# Base package for every SDK files.

import logging
import sys

import glog as log  # type: ignore
from glog import GlogFormatter  # type: ignore

log.setLevel("INFO")  # type: ignore


class _ColoredGlogFormatter(GlogFormatter):  # type: ignore
    """GlogFormatter that adds ANSI colors for WARNING and above when outputting to a terminal."""

    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if not sys.stderr.isatty():
            return msg
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{msg}{self.RESET}"
        if record.levelno >= logging.WARNING:
            return f"{self.YELLOW}{msg}{self.RESET}"
        return msg


# Replace glog's default formatter with our colored one
for _h in logging.getLogger().handlers:
    if isinstance(_h.formatter, GlogFormatter):
        _h.setFormatter(_ColoredGlogFormatter())
