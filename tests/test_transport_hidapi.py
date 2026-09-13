import pytest

pytest.importorskip("hid", reason="hidapi is only installed on Windows")

from logitech_flow_kvm.hidpp import transport_hidapi  # noqa: E402
from logitech_flow_kvm.hidpp.transport_hidapi import HidApiIO  # noqa: E402

DEVICE_PATH = r"\\?\HID#Dev_VID&02046d_PID&b034&Col02#9&8191b00&0&0001"


class FakeDevice:
    """Stands in for `hid.device`, recording writes and replaying reads."""

    def __init__(self):
        self.opened_path: bytes | None = None
        self.nonblocking: int | None = None
        self.closed = False
        self.written: list[bytes] = []
        self.reads: list[list[int]] = []
        self.read_timeouts: list[int] = []
        self.short_write = False

    def open_path(self, path: bytes) -> None:
        self.opened_path = path

    def set_nonblocking(self, value: int) -> int:
        self.nonblocking = value
        return 0

    def write(self, report: bytes) -> int:
        self.written.append(bytes(report))
        return len(report) - 1 if self.short_write else len(report)

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int]:
        self.read_timeouts.append(timeout_ms)
        return self.reads.pop(0) if self.reads else []

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def device(monkeypatch) -> FakeDevice:
    fake = FakeDevice()
    monkeypatch.setattr(transport_hidapi.hid, "device", lambda: fake)
    return fake


class TestOpen:
    def test_opens_the_encoded_path(self, device):
        HidApiIO(DEVICE_PATH)

        assert device.opened_path == DEVICE_PATH.encode()

    def test_sets_nonblocking_so_zero_timeout_reads_return(self, device):
        HidApiIO(DEVICE_PATH)

        assert device.nonblocking == 1

    def test_close_closes_the_device(self, device):
        HidApiIO(DEVICE_PATH).close()

        assert device.closed is True


class TestWrite:
    def test_builds_a_short_report(self, device):
        HidApiIO(DEVICE_PATH).write(0x01, b"\x81\x00", long_message=False)

        assert device.written == [b"\x10\x01\x81\x00\x00\x00\x00"]

    def test_builds_a_long_report(self, device):
        HidApiIO(DEVICE_PATH).write(0xFF, b"\x08\x10", long_message=True)

        assert device.written == [b"\x11\xff\x08\x10" + b"\x00" * 16]

    def test_uses_a_long_report_for_a_payload_that_cannot_fit(self, device):
        HidApiIO(DEVICE_PATH).write(0xFF, b"\x00" * 6, long_message=False)

        assert device.written[0][0] == transport_hidapi.LONG_MESSAGE_ID

    def test_raises_on_a_short_write(self, device):
        device.short_write = True

        with pytest.raises(OSError, match="short write"):
            HidApiIO(DEVICE_PATH).write(0x01, b"\x81\x00", long_message=False)


class TestRead:
    def test_splits_the_report_into_id_devnumber_and_payload(self, device):
        device.reads = [[0x11, 0xFF, 0x08, 0x10, 0x03]]

        assert HidApiIO(DEVICE_PATH).read(1.0) == (0x11, 0xFF, b"\x08\x10\x03")

    def test_returns_none_when_nothing_arrives(self, device):
        assert HidApiIO(DEVICE_PATH).read(1.0) is None

    def test_returns_none_for_a_truncated_report(self, device):
        device.reads = [[0x11]]

        assert HidApiIO(DEVICE_PATH).read(1.0) is None

    def test_converts_the_timeout_to_milliseconds(self, device):
        HidApiIO(DEVICE_PATH).read(0.25)

        assert device.read_timeouts == [250]


class TestDrain:
    def test_discards_everything_already_waiting(self, device):
        device.reads = [[0x11, 0xFF, 0x01], [0x11, 0xFF, 0x02]]

        io = HidApiIO(DEVICE_PATH)
        io.drain()

        assert device.reads == []
        assert device.read_timeouts == [0, 0, 0]
