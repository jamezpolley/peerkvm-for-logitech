import time

import hid

from .transport import LONG_MESSAGE_ID
from .transport import LONG_REPORT_SIZE
from .transport import MAX_READ_SIZE
from .transport import SHORT_MESSAGE_ID
from .transport import SHORT_REPORT_SIZE
from .transport import WRITE_RETRIES
from .transport import WRITE_RETRY_DELAY


class HidApiIO:
    """Read/write access to one HID collection through the `hidapi` library.

    The counterpart to `transport_linux.HidRawIO`, and the same caution applies:
    each thread that blocks on reads should open its own instance, or a read on
    one thread can consume the reply another thread is waiting for.
    """

    def __init__(self, path: str):
        self.path = path
        self._device = hid.device()
        self._device.open_path(path.encode())
        # Without this, a read with no timeout blocks forever rather than
        # returning empty, and `drain()` -- which reads with a zero timeout to
        # clear pending reports -- never returns.
        self._device.set_nonblocking(1)

    def close(self) -> None:
        self._device.close()

    def __enter__(self) -> "HidApiIO":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def write(self, devnumber: int, payload: bytes, long_message: bool) -> None:
        if long_message or len(payload) > SHORT_REPORT_SIZE - 2:
            body = payload.ljust(LONG_REPORT_SIZE - 2, b"\x00")
            report = bytes([LONG_MESSAGE_ID, devnumber]) + body
        else:
            body = payload.ljust(SHORT_REPORT_SIZE - 2, b"\x00")
            report = bytes([SHORT_MESSAGE_ID, devnumber]) + body

        written = 0
        for attempt in range(WRITE_RETRIES):
            try:
                written = self._device.write(report)
            except OSError:
                if attempt == WRITE_RETRIES - 1:
                    raise
                time.sleep(WRITE_RETRY_DELAY)
                continue
            break

        if written != len(report):
            raise OSError(f"short write: {written}/{len(report)} bytes")

    def read(self, timeout: float) -> tuple[int, int, bytes] | None:
        """Read one report, or None if nothing arrived within `timeout` seconds."""
        data = self._device.read(MAX_READ_SIZE, timeout_ms=int(timeout * 1000))
        if len(data) < 2:
            return None
        return data[0], data[1], bytes(data[2:])

    def drain(self) -> None:
        """Discard any reports already waiting to be read."""
        while self.read(0) is not None:
            pass
