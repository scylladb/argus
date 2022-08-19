import smtplib
from typing import List, Set
from smtplib import SMTPException

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app
from flask import render_template

class Email:
    #  pylint: disable=too-many-instance-attributes
    """
    Responsible for sending emails
    """
    _attachments_size_limit = 10485760  # 10Mb = 20 * 1024 * 1024
    _body_size_limit = 26214400  # 25Mb = 20 * 1024 * 1024

    def __init__(self):
        self.sender = ""
        self._password = ""
        self._user = ""
        self._server_host = ""
        self._server_port = ""
        self._conn = None
        self._retrieve_credentials()
        self._connect()

    def _retrieve_credentials(self):
        self.sender = current_app.config["EMAIL_SENDER"]
        self._password = current_app.config["EMAIL_SENDER_PASS"]
        self._user = current_app.config["EMAIL_SENDER_USER"]
        self._server_host = current_app.config["EMAIL_SERVER"]
        self._server_port = current_app.config["EMAIL_SERVER_PORT"]

    def _connect(self):
        self.conn = smtplib.SMTP(host=self._server_host, port=self._server_port)
        self.conn.ehlo()
        self.conn.starttls()
        self.conn.login(user=self._user, password=self._password)

    def _is_connection_open(self):
        try:
            status, _ = self.conn.noop()
        except SMTPException:
            status = -1

        return True if status == 250 else False

    def _prepare_email(self, subject:str,
                      content: str,
                      recipients: List[str],
                      html: bool = True):  # pylint: disable=too-many-arguments
        msg = MIMEMultipart()
        msg['subject'] = subject
        msg['from'] = self.sender
        assert recipients, "No recipients provided"
        msg['to'] = ','.join(recipients)
        if html:
            text_part = MIMEText(content, "html")
        else:
            text_part = MIMEText(content, "plain")
        msg.attach(text_part)
        email = msg.as_string()
        return email

    def send(self, subject, content, recipients, html=True):  # pylint: disable=too-many-arguments
        """
        :param subject: text
        :param content: text/html
        :param recipients: iterable, list of recipients
        :param html: True/False
        :param files: paths of the files that will be attached to the email
        :return:
        """
        email = self._prepare_email(subject, content, recipients, html)
        self._send_email(recipients, email)

    def _send_email(self, recipients, email):
        if not self._is_connection_open():
            self._connect()
        self.conn.sendmail(self.sender, recipients, email)

    def __del__(self):
        self.conn.quit()
