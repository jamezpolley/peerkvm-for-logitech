"""Watching for HID devices arriving and leaving, per platform.

A device switching hosts looks like a disconnect on the host it left and a
connect on the host it reached, so noticing those promptly is what lets a node
react without being restarted.
"""

import sys
from collections.abc import Callable
from typing import Protocol


class HotplugMonitor(Protocol):
    """Calls back with ("add" | "remove", path) as devices come and go."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


def create_hotplug_monitor(callback: Callable[[str, str], None]) -> HotplugMonitor:
    """Build the hotplug monitor this platform can offer.

    The implementations are imported here rather than at module scope so that
    neither platform's dependencies are loaded on the other.
    """
    if sys.platform == "win32":
        from .hotplug_polling import HidPollMonitor

        return HidPollMonitor(callback)

    from .udev_monitor import HidrawUdevMonitor

    return HidrawUdevMonitor(callback)
