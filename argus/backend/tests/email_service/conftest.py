import logging
import pytest

from argus.backend.service.email_service import EmailService
from argus.backend.util.send_email import Attachment, Email

LOGGER = logging.getLogger(__name__)

class EmailListener(Email):
    def __init__(self, init_connection=True):
        self.subject_line: str | None = None
        self.content: str | None = None
        self.recipients: list[str] | None = None
        self.attachments: list[Attachment] | None = None

    def __del__(self):
        pass

    def send(self, subject: str, content: str, recipients: list[str], html=True, attachments = None):
        self.subject_line = subject
        self.content = content
        self.recipients = recipients
        self.attachments = attachments



@pytest.fixture(scope='function')
def email_listener() -> EmailListener:
    listener = EmailListener()
    EmailService.set_sender(listener)
    yield listener
    EmailService.set_sender(None)
