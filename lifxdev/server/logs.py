#!/usr/bin/env python3

from __future__ import annotations

import logging
from collections.abc import Callable

import coloredlogs


def log_exception(error: Exception, log_func: Callable) -> None:
    """Log a error

    Args:
        error: Any python exception.
        log_func: The function used to log the error.
    """
    err_type = type(error).__name__
    err_str = str(error)
    log_func(f"{err_type}: {err_str}")


def setup(level: int = logging.INFO) -> None:
    """Set up the logger with a log level."""
    coloredlogs.install(level=level, fmt="%(asctime)s %(levelname)s %(message)s")
