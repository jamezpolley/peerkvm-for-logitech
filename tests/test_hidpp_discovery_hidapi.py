import pytest

pytest.importorskip("hid", reason="hidapi is only installed on Windows")

from logitech_flow_kvm.hidpp import discovery_hidapi as discovery  # noqa: E402

BLUETOOTH = discovery.HIDAPI_BUS_BLUETOOTH
USB = 0x01

MOUSE_PATH = rb"\\?\HID#Dev_VID&02046d_PID&b034&Col02#9&8191b00&0&0001"
KEYBOARD_PATH = rb"\\?\HID#Dev_VID&02046d_PID&b383&Col05#9&2080149d&0&0004"


def _entry(**overrides) -> dict:
    entry = {
        "path": MOUSE_PATH,
        "vendor_id": discovery.LOGITECH_VENDOR_ID,
        "product_id": 0xB034,
        "serial_number": "dea2d8ea69df",
        "product_string": "MX_Master_3S",
        "usage_page": 0xFF43,
        "usage": 0x0202,
        "interface_number": -1,
        "bus_type": BLUETOOTH,
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def enumeration(monkeypatch):
    """Drive discovery from a canned enumeration, with every path answering."""

    def install(entries: list[dict], long_report_paths: set | None = None) -> None:
        monkeypatch.setattr(discovery, "enumerate_devices", lambda: entries)
        accepted = (
            {entry["path"] for entry in entries}
            if long_report_paths is None
            else long_report_paths
        )
        monkeypatch.setattr(
            discovery, "declares_long_report", lambda path: path in accepted
        )

    return install


class TestFindDirectDevices:
    def test_returns_a_bluetooth_device_declaring_the_long_report(self, enumeration):
        enumeration([_entry()])

        devices = discovery.find_direct_devices()

        assert len(devices) == 1
        device = devices[0]
        assert device.path == MOUSE_PATH.decode()
        assert device.product_id == 0xB034
        assert device.serial == "dea2d8ea69df"
        assert device.name == "MX_Master_3S"
        assert device.bus_id == discovery.BLUETOOTH_BUS_ID
        assert device.hidpp_long is True

    def test_ignores_collections_without_the_long_report(self, enumeration):
        # A keyboard publishes several collections; only the HID++ one answers.
        other = _entry(path=KEYBOARD_PATH, usage_page=0xFF0C, usage=0x0001)
        enumeration([_entry(), other], long_report_paths={MOUSE_PATH})

        devices = discovery.find_direct_devices()

        assert [device.path for device in devices] == [MOUSE_PATH.decode()]

    def test_ignores_devices_not_reached_over_bluetooth(self, enumeration):
        enumeration([_entry(bus_type=USB)])

        assert discovery.find_direct_devices() == []

    def test_ignores_devices_with_an_unreported_bus(self, enumeration):
        entry = _entry()
        del entry["bus_type"]
        enumeration([entry])

        assert discovery.find_direct_devices() == []

    def test_treats_empty_strings_as_missing(self, enumeration):
        enumeration([_entry(product_string="", serial_number="")])

        device = discovery.find_direct_devices()[0]

        assert device.name is None
        assert device.serial is None

    def test_orders_devices_by_path(self, enumeration):
        enumeration([_entry(path=KEYBOARD_PATH), _entry(path=MOUSE_PATH)])

        devices = discovery.find_direct_devices()

        assert [device.path for device in devices] == sorted(
            [KEYBOARD_PATH.decode(), MOUSE_PATH.decode()]
        )


class TestFindReceivers:
    def test_reports_no_receivers(self):
        assert discovery.find_receivers() == []
