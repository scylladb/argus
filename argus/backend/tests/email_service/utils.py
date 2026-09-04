
from argus.backend.util.send_email import Attachment, Email


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
