import sys

from .protocol import Transport

SHORT_MESSAGE_ID = 0x10
LONG_MESSAGE_ID = 0x11
SHORT_REPORT_SIZE = 7
LONG_REPORT_SIZE = 20
MAX_READ_SIZE = 32

WRITE_RETRIES = 3
WRITE_RETRY_DELAY = 0.1


def open_transport(path: str) -> Transport:
    """Open `path` using the HID backend available on this platform.

    The backends are imported here rather than at module scope so that neither
    platform's dependencies are loaded on the other: the hidapi backend needs a
    package that is only installed on Windows.
    """
    if sys.platform == "win32":
        from .transport_hidapi import HidApiIO

        return HidApiIO(path)

    from .transport_linux import HidRawIO

    return HidRawIO(path)
