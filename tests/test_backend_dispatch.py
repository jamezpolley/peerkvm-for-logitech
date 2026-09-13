"""The per-platform backends are selected at call time, not import time.

Only one branch of each dispatcher ever runs on a given machine, so a mistake
in the other would otherwise stay hidden until someone ran the project on the
other platform.
"""

import sys

import pytest

from logitech_flow_kvm import hotplug
from logitech_flow_kvm import udev_monitor
from logitech_flow_kvm.hidpp import transport
from logitech_flow_kvm.hidpp import transport_linux


def _noop(action: str, path: str) -> None:
    pass


class TestOpenTransport:
    def test_opens_a_hidraw_node_on_linux(self, monkeypatch):
        opened: list[str] = []
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(transport_linux, "HidRawIO", opened.append)

        transport.open_transport("/dev/hidraw9")

        assert opened == ["/dev/hidraw9"]

    def test_opens_through_hidapi_on_windows(self, monkeypatch):
        transport_hidapi = pytest.importorskip(
            "logitech_flow_kvm.hidpp.transport_hidapi",
            reason="hidapi is only installed on Windows",
        )
        opened: list[str] = []
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(transport_hidapi, "HidApiIO", opened.append)

        transport.open_transport(r"\\?\HID#Dev_VID&02046d")

        assert opened == [r"\\?\HID#Dev_VID&02046d"]


class TestCreateHotplugMonitor:
    def test_watches_uevents_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")

        monitor = hotplug.create_hotplug_monitor(_noop)

        assert isinstance(monitor, udev_monitor.HidrawUdevMonitor)

    def test_polls_on_windows(self, monkeypatch):
        hotplug_polling = pytest.importorskip(
            "logitech_flow_kvm.hotplug_polling",
            reason="hidapi is only installed on Windows",
        )
        monkeypatch.setattr(sys, "platform", "win32")

        monitor = hotplug.create_hotplug_monitor(_noop)

        assert isinstance(monitor, hotplug_polling.HidPollMonitor)
