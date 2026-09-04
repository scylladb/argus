import logging
import pytest

from argus.backend.service.email_service import EmailService
from argus.backend.tests.email_service.utils import EmailListener

LOGGER = logging.getLogger(__name__)

@pytest.fixture(scope='function')
def email_listener() -> EmailListener:
    listener = EmailListener()
    EmailService.set_sender(listener)
    yield listener
    EmailService.set_sender(None)
