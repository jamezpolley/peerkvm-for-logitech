import os

from logitech_flow_kvm.hidpp import discovery_linux as discovery


def _write_uevent(root, name: str, lines: list[str]) -> None:
    device_dir = os.path.join(root, name, "device")
    os.makedirs(device_dir, exist_ok=True)
    with open(os.path.join(device_dir, "uevent"), "w") as f:
        f.write("\n".join(lines) + "\n")


def _write_report_descriptor(root, name: str, descriptor: bytes) -> None:
    device_dir = os.path.join(root, name, "device")
    with open(os.path.join(device_dir, "report_descriptor"), "wb") as f:
        f.write(descriptor)


class TestParseInterfaceNumber:
    def test_extracts_trailing_interface_digits(self):
        assert discovery._parse_interface_number("usb-0000:00:14.0-5.1.4/input2") == 2

    def test_extracts_interface_number_before_extra_suffix(self):
        assert discovery._parse_interface_number("usb-0000:00:14.0-5.1.4/input2:1") == 2

    def test_returns_none_without_input_segment(self):
        assert discovery._parse_interface_number("usb-0000:00:14.0-5.1.4") is None

    def test_returns_none_for_empty_string(self):
        assert discovery._parse_interface_number("") is None


class TestFindReceivers:
    def test_finds_known_receiver_on_the_expected_interface(
        self, tmp_path, monkeypatch
    ):
        _write_uevent(
            str(tmp_path),
            "hidraw4",
            [
                "DRIVER=hid-generic",
                "HID_ID=0003:0000046D:0000C548",
                "HID_NAME=Logitech USB Receiver",
                "HID_PHYS=usb-0000:00:14.0-5.1.2/input2",
            ],
        )
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        receivers = discovery.find_receivers()

        assert len(receivers) == 1
        assert receivers[0].path == "/dev/hidraw4"
        assert receivers[0].kind == "bolt"
        assert receivers[0].product_id == 0xC548

    def test_ignores_wrong_usb_interface(self, tmp_path, monkeypatch):
        _write_uevent(
            str(tmp_path),
            "hidraw2",
            [
                "DRIVER=hid-generic",
                "HID_ID=0003:0000046D:0000C548",
                "HID_PHYS=usb-0000:00:14.0-5.1.2/input0",
            ],
        )
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        assert discovery.find_receivers() == []


class TestFindDirectDevices:
    def test_finds_logitech_bluetooth_device_with_long_hidpp_report(
        self, tmp_path, monkeypatch
    ):
        _write_uevent(
            str(tmp_path),
            "hidraw2",
            [
                "HID_ID=0005:0000046D:0000B369",
                "HID_NAME=MX Keys Mini",
                "HID_UNIQ=d7:c3:34:36:65:db",
            ],
        )
        _write_report_descriptor(str(tmp_path), "hidraw2", b"\x06\x43\xff\x85\x11")
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        devices = discovery.find_direct_devices()

        assert len(devices) == 1
        assert devices[0].path == "/dev/hidraw2"
        assert devices[0].product_id == 0xB369
        assert devices[0].name == "MX Keys Mini"
        assert devices[0].serial == "d7:c3:34:36:65:db"

    def test_ignores_bluetooth_device_without_hidpp_report(self, tmp_path, monkeypatch):
        _write_uevent(str(tmp_path), "hidraw3", ["HID_ID=0005:0000046D:0000B369"])
        _write_report_descriptor(str(tmp_path), "hidraw3", b"\x05\x01\x85\x01")
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        assert discovery.find_direct_devices() == []


class TestFindReceiversContinued:
    def test_ignores_non_logitech_vendor(self, tmp_path, monkeypatch):
        _write_uevent(
            str(tmp_path),
            "hidraw0",
            [
                "DRIVER=hid-generic",
                "HID_ID=0018:000032AC:00000006",
                "HID_PHYS=i2c-FRMW0001:00",
            ],
        )
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        assert discovery.find_receivers() == []

    def test_ignores_unknown_logitech_product(self, tmp_path, monkeypatch):
        _write_uevent(
            str(tmp_path),
            "hidraw3",
            [
                "DRIVER=hid-generic",
                "HID_ID=0003:0000046D:00004099",
                "HID_PHYS=usb-0000:00:14.0-5.1.2/input2",
            ],
        )
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        assert discovery.find_receivers() == []

    def test_finds_unifying_receiver(self, tmp_path, monkeypatch):
        _write_uevent(
            str(tmp_path),
            "hidraw5",
            [
                "DRIVER=logitech-djreceiver",
                "HID_ID=0003:0000046D:0000C52B",
                "HID_PHYS=usb-0000:00:14.0-5.1.4/input2",
            ],
        )
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        receivers = discovery.find_receivers()

        assert len(receivers) == 1
        assert receivers[0].kind == "unifying"

    def test_missing_uevent_is_skipped_without_error(self, tmp_path, monkeypatch):
        os.makedirs(tmp_path / "hidraw1" / "device", exist_ok=True)
        monkeypatch.setattr(discovery, "HIDRAW_SYSFS_GLOB", str(tmp_path / "hidraw*"))

        assert discovery.find_receivers() == []
