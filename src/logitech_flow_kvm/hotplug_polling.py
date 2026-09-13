import logging
import threading
from collections.abc import Callable

import hid

from .hidpp.discovery_hidapi import LOGITECH_VENDOR_ID

logger = logging.getLogger(__name__)

# Enumeration costs a few milliseconds, so polling this often is cheap while
# keeping the delay before a node notices a device well under a second.
POLL_INTERVAL = 0.5


class HidPollMonitor:
    """Notice Logitech HID devices arriving and leaving, by polling for them.

    Windows publishes no uevent stream to read, and `WM_DEVICECHANGE` needs a
    hidden window and a message loop to receive, so this polls the same
    enumeration that discovery uses.

    It watches every collection a device publishes rather than only the HID++
    one, which keeps a poll to a single cheap enumeration with no device opened
    to read its report descriptor. One device therefore reports several
    additions at once; callers already debounce, so that costs nothing.
    """

    def __init__(
        self,
        callback: Callable[[str, str], None],
        interval: float = POLL_INTERVAL,
    ):
        self.callback = callback
        self._interval = interval
        self._known: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # Take the baseline before the thread runs, so devices already present
        # are not announced as new arrivals.
        self._known = self._paths()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _paths(self) -> set[str]:
        return {info["path"].decode() for info in hid.enumerate(LOGITECH_VENDOR_ID)}

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                current = self._paths()
            except OSError:
                logger.exception("Could not enumerate HID devices")
                continue

            for path in sorted(current - self._known):
                self.callback("add", path)
            for path in sorted(self._known - current):
                self.callback("remove", path)
            self._known = current
