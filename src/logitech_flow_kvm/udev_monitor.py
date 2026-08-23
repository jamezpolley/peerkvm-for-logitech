import os
import socket
import threading
from collections.abc import Callable

NETLINK_KOBJECT_UEVENT = 15
UEVENT_BUFFER_SIZE = 64 * 1024


def parse_uevent(data: bytes) -> dict[str, str]:
    properties: dict[str, str] = {}
    for item in data.rstrip(b"\0").split(b"\0"):
        try:
            text = item.decode()
        except UnicodeDecodeError:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            properties[key] = value
        elif "@" in text and "ACTION" not in properties:
            properties["ACTION"] = text.split("@", 1)[0]
    return properties


class HidrawUdevMonitor:
    """Watch kernel uevents directly; receiving these does not require root."""

    def __init__(self, callback: Callable[[str, str], None]):
        self.callback = callback
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        sock = socket.socket(
            socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_KOBJECT_UEVENT
        )
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, UEVENT_BUFFER_SIZE)
        sock.bind((os.getpid(), 1))
        sock.settimeout(1.0)
        self._socket = sock
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                properties = parse_uevent(self._socket.recv(UEVENT_BUFFER_SIZE))
            except TimeoutError:
                continue
            except OSError:
                if not self._stop.is_set():
                    raise
                return
            if properties.get("SUBSYSTEM") != "hidraw":
                continue
            action = properties.get("ACTION")
            devname = properties.get("DEVNAME")
            if action in {"add", "remove"} and devname:
                self.callback(action, f"/dev/{devname.removeprefix('/dev/')}")
