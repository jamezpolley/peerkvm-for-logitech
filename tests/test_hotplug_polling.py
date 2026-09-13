import threading

import pytest

pytest.importorskip("hid", reason="hidapi is only installed on Windows")

from logitech_flow_kvm import hotplug_polling  # noqa: E402
from logitech_flow_kvm.hotplug_polling import HidPollMonitor  # noqa: E402

MOUSE = rb"\\?\HID#Dev_VID&02046d_PID&b034&Col02"
KEYBOARD = rb"\\?\HID#Dev_VID&02046d_PID&b383&Col05"

POLL = 0.01
DEADLINE = 5.0


class FakeHid:
    """Replays a sequence of enumeration results, one per call.

    The last state repeats once the sequence runs out, so the monitor settles
    rather than looping over the same change forever. A state given as an
    exception is raised instead, standing in for enumeration failing.
    """

    def __init__(self, states):
        self._states = list(states)
        self._calls = 0
        self.lock = threading.Lock()

    def enumerate(self, vendor_id=0):
        with self.lock:
            index = min(self._calls, len(self._states) - 1)
            self._calls += 1
        state = self._states[index]
        if isinstance(state, Exception):
            raise state
        return [{"path": path} for path in state]


def _run(monkeypatch, states, expected_count):
    """Run a monitor over `states`, returning the events it reported."""
    monkeypatch.setattr(hotplug_polling, "hid", FakeHid(states))
    events: list[tuple[str, str]] = []
    seen = threading.Event()

    def record(action: str, path: str) -> None:
        events.append((action, path))
        if len(events) >= expected_count:
            seen.set()

    monitor = HidPollMonitor(record, interval=POLL)
    monitor.start()
    try:
        if expected_count:
            assert seen.wait(DEADLINE), f"only saw {events}"
        else:
            seen.wait(0.2)
    finally:
        monitor.stop()
    return events


def test_reports_a_device_that_appears(monkeypatch):
    events = _run(monkeypatch, [{MOUSE}, {MOUSE, KEYBOARD}], expected_count=1)

    assert events == [("add", KEYBOARD.decode())]


def test_reports_a_device_that_disappears(monkeypatch):
    events = _run(monkeypatch, [{MOUSE, KEYBOARD}, {MOUSE}], expected_count=1)

    assert events == [("remove", KEYBOARD.decode())]


def test_reports_every_collection_of_an_arriving_device(monkeypatch):
    # One device publishes several collections; callers debounce them.
    events = _run(monkeypatch, [set(), {MOUSE, KEYBOARD}], expected_count=2)

    assert sorted(events) == [
        ("add", MOUSE.decode()),
        ("add", KEYBOARD.decode()),
    ]


def test_devices_already_present_are_not_announced(monkeypatch):
    events = _run(monkeypatch, [{MOUSE, KEYBOARD}], expected_count=0)

    assert events == []


def test_keeps_polling_after_enumeration_fails(monkeypatch):
    states = [{MOUSE}, OSError("device gone"), {MOUSE, KEYBOARD}]

    events = _run(monkeypatch, states, expected_count=1)

    assert events == [("add", KEYBOARD.decode())]


def test_stop_ends_the_polling_thread(monkeypatch):
    monkeypatch.setattr(hotplug_polling, "hid", FakeHid([{MOUSE}]))
    monitor = HidPollMonitor(lambda action, path: None, interval=POLL)

    monitor.start()
    thread = monitor._thread
    monitor.stop()

    assert thread is not None
    assert not thread.is_alive()
