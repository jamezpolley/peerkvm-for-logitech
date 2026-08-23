from logitech_flow_kvm.udev_monitor import parse_uevent


def test_parse_kernel_uevent():
    event = parse_uevent(
        b"add@/devices/example\0ACTION=add\0SUBSYSTEM=hidraw\0"
        b"DEVNAME=hidraw9\0"
    )

    assert event == {
        "ACTION": "add",
        "SUBSYSTEM": "hidraw",
        "DEVNAME": "hidraw9",
    }


def test_parse_skips_invalid_utf8_fields():
    assert parse_uevent(b"remove@/x\0\xff\0SUBSYSTEM=hidraw\0") == {
        "ACTION": "remove",
        "SUBSYSTEM": "hidraw",
    }
