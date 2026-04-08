# Base package for every SDK files.

import logging

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
        if not self._stream_is_tty:
            return msg
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{msg}{self.RESET}"
        if record.levelno >= logging.WARNING:
            return f"{self.YELLOW}{msg}{self.RESET}"
        return msg


# Replace glog's default formatter with our colored one only on TTY streams
for _h in logging.getLogger().handlers:
    if isinstance(_h, logging.StreamHandler) and isinstance(_h.formatter, GlogFormatter):
        formatter = _ColoredGlogFormatter()
        formatter._stream_is_tty = hasattr(_h, "stream") and hasattr(_h.stream, "isatty") and _h.stream.isatty()
        _h.setFormatter(formatter)
