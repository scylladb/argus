import logging
import shutil
import sys


class StatusLine:
    """A single terminal line that redraws in place."""

    def __init__(self, stream=None):
        self._stream = stream if stream is not None else sys.stdout
        self._text = ""
        self.enabled = bool(getattr(self._stream, "isatty", lambda: False)())

    @property
    def text(self) -> str:
        return self._text

    def set(self, text: str) -> None:
        if not self.enabled:
            return
        width = shutil.get_terminal_size(fallback=(120, 24)).columns - 1
        self._erase()
        self._text = text[:width]
        self._stream.write(self._text)
        self._stream.flush()

    def clear(self) -> None:
        if not self.enabled:
            return
        self._erase()
        self._stream.flush()

    def finish(self) -> None:
        if not self.enabled or not self._text:
            return
        self._stream.write("\n")
        self._text = ""
        self._stream.flush()

    def _erase(self) -> None:
        if self._text:
            self._stream.write("\r\x1b[2K")
            self._text = ""


class StatusLineHandler(logging.StreamHandler):
    """Stream handler that keeps a StatusLine below the records it writes."""

    def __init__(self, status: StatusLine, stream=None):
        super().__init__(stream)
        self._status = status

    def emit(self, record: logging.LogRecord) -> None:
        restore = self._status.text
        self._status.clear()
        super().emit(record)
        if restore:
            self._status.set(restore)
