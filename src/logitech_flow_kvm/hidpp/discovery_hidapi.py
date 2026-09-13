"""Device discovery through the `hidapi` library, used on Windows.

The acceptance rules mirror `discovery_linux`: a direct device is a Logitech
device reached over Bluetooth whose HID collection declares the long (0x11)
HID++ report.  Logitech devices publish several collections -- a keyboard
publishes six -- and only the HID++ one answers the protocol, so the report
descriptor is what distinguishes them, exactly as it does on Linux.
"""

import hid

from .models import DirectDeviceInfo
from .models import ReceiverInfo

LOGITECH_VENDOR_ID = 0x046D

# hidapi's own bus enum (hid_bus_type), unrelated to the kernel bus ids that
# `discovery_linux` reads out of sysfs.
HIDAPI_BUS_BLUETOOTH = 0x02

# What gets recorded on DirectDeviceInfo, so the field carries the same meaning
# whichever backend produced it instead of leaking hidapi's enum.
BLUETOOTH_BUS_ID = 0x0005

# "Report ID (0x11)" in a HID report descriptor.
LONG_REPORT_DECLARATION = b"\x85\x11"


def enumerate_devices() -> list[dict]:
    """Every Logitech HID collection hidapi can see. The seam tests replace."""
    return hid.enumerate(LOGITECH_VENDOR_ID)


def declares_long_report(path: bytes) -> bool:
    """Whether the collection at `path` declares the long HID++ report."""
    device = hid.device()
    try:
        device.open_path(path)
    except OSError:
        return False
    try:
        return LONG_REPORT_DECLARATION in bytes(device.get_report_descriptor())
    except (OSError, ValueError):
        return False
    finally:
        device.close()


def find_receivers() -> list[ReceiverInfo]:
    """Always empty: receiver support is not implemented on this backend yet.

    Kept so callers can enumerate both kinds without caring which backend is in
    use. Directly-connected devices work without it.
    """
    return []


def find_direct_devices() -> list[DirectDeviceInfo]:
    """Enumerate directly-connected Logitech Bluetooth HID++ devices."""
    found = []
    for info in sorted(enumerate_devices(), key=lambda item: item["path"]):
        if info.get("bus_type") != HIDAPI_BUS_BLUETOOTH:
            continue
        path = info["path"]
        if not declares_long_report(path):
            continue

        found.append(
            DirectDeviceInfo(
                path=path.decode(),
                product_id=info["product_id"],
                name=info.get("product_string") or None,
                serial=info.get("serial_number") or None,
                bus_id=BLUETOOTH_BUS_ID,
                hidpp_long=True,
            )
        )
    return found
