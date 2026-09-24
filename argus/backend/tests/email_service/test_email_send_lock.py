import asyncio
import threading
import time

from argus.backend.util.send_email import Email


class RecordingSMTP:
    def __init__(self):
        self.in_flight = 0
        self.peak = 0
        self.sent = []
        self._guard = threading.Lock()

    def noop(self):
        return 250, b"OK"

    def sendmail(self, sender, recipients, email):
        with self._guard:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        time.sleep(0.02)
        with self._guard:
            self.in_flight -= 1
            self.sent.append(recipients)

    def quit(self):
        pass


async def test_concurrent_sends_use_the_connection_one_at_a_time():
    email = Email(init_connection=False)
    email.sender = "argus@example.com"
    smtp = RecordingSMTP()
    email._connection = smtp

    await asyncio.gather(*(
        asyncio.to_thread(email.send, "subject", "body", [f"user{i}@example.com"], html=False)
        for i in range(5)
    ))

    assert smtp.peak == 1
    assert sorted(r[0] for r in smtp.sent) == [f"user{i}@example.com" for i in range(5)]
