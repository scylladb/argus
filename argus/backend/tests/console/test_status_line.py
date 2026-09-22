import io
import logging
import os

from argus.backend.util.console import StatusLine, StatusLineHandler

ERASE = "\r\x1b[2K"


class FakeTerminal(io.StringIO):
    def isatty(self):
        return True


def test_writes_the_text_when_the_stream_is_a_terminal():
    stream = FakeTerminal()

    StatusLine(stream).set("scanning")

    assert stream.getvalue() == "scanning"


def test_erases_the_previous_text_before_the_next_one():
    stream = FakeTerminal()
    status = StatusLine(stream)

    status.set("first")
    status.set("second")

    assert stream.getvalue() == f"first{ERASE}second"


def test_writes_nothing_when_the_stream_is_not_a_terminal():
    stream = io.StringIO()

    status = StatusLine(stream)
    status.set("scanning")
    status.finish()

    assert status.enabled is False
    assert stream.getvalue() == ""


def test_finish_closes_the_line_once():
    stream = FakeTerminal()
    status = StatusLine(stream)
    status.set("scanning")

    status.finish()
    status.finish()

    assert stream.getvalue() == "scanning\n"


def test_truncates_text_that_would_wrap(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=None: os.terminal_size((11, 24)))
    stream = FakeTerminal()

    StatusLine(stream).set("0123456789abcdef")

    assert stream.getvalue() == "0123456789"


def test_a_log_record_is_written_above_the_restored_status_line():
    status_stream = FakeTerminal()
    log_stream = FakeTerminal()
    status = StatusLine(status_stream)
    status.set("scanning")

    handler = StatusLineHandler(status, stream=log_stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("t", logging.WARNING, __file__, 1, "a warning", None, None))

    assert log_stream.getvalue() == "a warning\n"
    assert status_stream.getvalue() == f"scanning{ERASE}scanning"


def test_one_shared_stream_keeps_the_record_above_the_line():
    stream = FakeTerminal()
    status = StatusLine(stream)
    status.set("scanning")

    handler = StatusLineHandler(status, stream=stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("t", logging.WARNING, __file__, 1, "a warning", None, None))

    assert stream.getvalue() == f"scanning{ERASE}a warning\nscanning"
