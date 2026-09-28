"""Logging for the health process."""

import logging

from argus.backend.util.logsetup import setup_application_logging

RUNNER_LOGGER = "qatools_health"


def configure_logging(log_level: int | str = logging.INFO) -> None:
    """Set up the Argus log handlers and route the runner log through them.

    setup_application_logging calls dictConfig, which disables every logger it
    does not name. The runner logger exists by then, so it is enabled again
    here, or its status transitions never reach the log.
    """
    setup_application_logging(log_level=log_level)
    runner_logger = logging.getLogger(RUNNER_LOGGER)
    runner_logger.setLevel(logging.INFO)
    for handler in logging.getLogger("argus").handlers:
        if handler not in runner_logger.handlers:
            runner_logger.addHandler(handler)
    runner_logger.disabled = False
