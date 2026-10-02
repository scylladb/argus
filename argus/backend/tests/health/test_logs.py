import logging

from qatools_health import runner  # noqa: F401

from argus.backend.service.health.logs import RUNNER_LOGGER, configure_logging


def test_runner_log_survives_the_application_log_setup():
    runner_logger = logging.getLogger(RUNNER_LOGGER)
    configure_logging(logging.INFO)
    assert runner_logger.disabled is False
    assert runner_logger.isEnabledFor(logging.INFO)
    assert set(logging.getLogger("argus").handlers) <= set(runner_logger.handlers)


def test_runner_log_follows_the_application_log_level():
    runner_logger = logging.getLogger(RUNNER_LOGGER)
    configure_logging(logging.WARNING)
    try:
        assert not runner_logger.isEnabledFor(logging.INFO)
        assert runner_logger.isEnabledFor(logging.WARNING)
    finally:
        configure_logging(logging.INFO)
